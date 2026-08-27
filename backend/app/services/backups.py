from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AuditLog, BackupSchedule, Organization, User, utc_now
from app.storage import ObjectStorage, get_object_storage
from app.vrp.scheduling import calculate_next_run

BACKUP_FORMAT_VERSION = "1"
BACKUP_CONTENT_TYPE = "application/zip"
SENSITIVE_COLUMN_PARTS = (
    "password",
    "token_hash",
    "secret",
    "api_key",
    "routing_token",
    "recovery_code",
    "challenge",
)
EXCLUDED_TABLES = {
    "api_tokens",
    "backup_schedules",
    "mfa_challenges",
    "refresh_sessions",
    "user_mfa_methods",
    "user_mfa_recovery_codes",
}


class BackupBusyError(RuntimeError):
    pass


class BackupNotAvailableError(RuntimeError):
    pass


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Mapping):
        serialized: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if any(part in text_key.casefold() for part in SENSITIVE_COLUMN_PARTS):
                serialized[text_key] = "[REDACTED]"
            else:
                serialized[text_key] = _json_value(item)
        return serialized
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return str(value)


def _safe_filename(value: str, fallback: str) -> str:
    normalized = Path(value).name.strip()
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized).strip(".-")
    return normalized[:180] or fallback


class BackupService:
    def __init__(
        self,
        session: Session,
        *,
        storage: ObjectStorage | None = None,
    ):
        self.session = session
        self.storage = storage or get_object_storage()

    def get_schedule(self, organization_id: str) -> BackupSchedule:
        schedule = self.session.get(BackupSchedule, organization_id)
        if schedule is None:
            schedule = BackupSchedule(organization_id=organization_id)
            self.session.add(schedule)
            self.session.commit()
            self.session.refresh(schedule)
        return schedule

    def update_schedule(
        self,
        *,
        user: User,
        enabled: bool,
        frequency: str,
        backup_time: time,
        timezone: str,
        weekly_day: str,
        monthly_rule: str,
        correlation_id: str,
    ) -> BackupSchedule:
        schedule = self.session.get(
            BackupSchedule,
            user.organization_id,
            with_for_update=True,
        )
        if schedule is None:
            schedule = BackupSchedule(organization_id=user.organization_id)
            self.session.add(schedule)
        schedule.enabled = enabled
        schedule.frequency = frequency
        schedule.backup_time = backup_time
        schedule.timezone = timezone
        schedule.weekly_day = weekly_day
        schedule.monthly_rule = monthly_rule
        schedule.next_run_at = (
            calculate_next_run(
                frequency=frequency,
                processing_time=backup_time,
                timezone_name=timezone,
                weekly_day=weekly_day,
                monthly_rule=monthly_rule,
            )
            if enabled
            else None
        )
        schedule.updated_by = user.id
        schedule.last_error_message = None
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="backup.schedule_updated",
                entity_type="backup_schedule",
                entity_id=user.organization_id,
                correlation_id=correlation_id,
                details={
                    "enabled": enabled,
                    "frequency": frequency,
                    "backup_time": backup_time.isoformat(),
                    "timezone": timezone,
                    "weekly_day": weekly_day,
                    "monthly_rule": monthly_rule,
                },
            )
        )
        self.session.commit()
        self.session.refresh(schedule)
        return schedule

    def generate_now(self, *, user: User, correlation_id: str) -> BackupSchedule:
        return self.generate(
            organization_id=user.organization_id,
            actor_id=user.id,
            correlation_id=correlation_id,
            scheduled=False,
        )

    def generate(
        self,
        *,
        organization_id: str,
        actor_id: str | None,
        correlation_id: str,
        scheduled: bool,
    ) -> BackupSchedule:
        schedule = self.session.get(
            BackupSchedule,
            organization_id,
            with_for_update=True,
        )
        if schedule is None:
            schedule = BackupSchedule(organization_id=organization_id)
            self.session.add(schedule)
            self.session.flush()
        if schedule.last_status == "PROCESSING" or (
            schedule.last_status == "QUEUED" and not scheduled
        ):
            self.session.rollback()
            raise BackupBusyError("Már folyamatban van egy biztonsági mentés.")
        schedule.last_status = "PROCESSING"
        schedule.last_error_message = None
        self.session.commit()

        generated_at = utc_now()
        object_key = f"backups/{organization_id}/latest.zip"
        filename = "ai-raktar-biztonsagi-mentes.zip"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="ai-raktar-backup-",
                suffix=".zip",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
            self._write_archive(
                temporary_path,
                organization_id=organization_id,
                generated_at=generated_at,
            )
            digest = hashlib.sha256()
            with temporary_path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
            size_bytes = temporary_path.stat().st_size
            self.storage.put_file(
                temporary_path,
                object_key,
                BACKUP_CONTENT_TYPE,
            )

            schedule = self.session.get(
                BackupSchedule,
                organization_id,
                with_for_update=True,
            )
            schedule.last_run_at = generated_at
            schedule.last_status = "COMPLETED"
            schedule.last_error_message = None
            schedule.last_object_key = object_key
            schedule.last_filename = filename
            schedule.last_size_bytes = size_bytes
            schedule.last_sha256 = digest.hexdigest()
            self.session.add(
                AuditLog(
                    organization_id=organization_id,
                    actor_id=actor_id,
                    action="backup.generated",
                    entity_type="backup",
                    entity_id=organization_id,
                    correlation_id=correlation_id,
                    details={
                        "scheduled": scheduled,
                        "filename": filename,
                        "size_bytes": size_bytes,
                        "sha256": schedule.last_sha256,
                        "overwrote_previous": True,
                    },
                )
            )
            self.session.commit()
            self.session.refresh(schedule)
            return schedule
        except Exception as exc:
            self.session.rollback()
            schedule = self.session.get(BackupSchedule, organization_id)
            if schedule is not None:
                schedule.last_status = "FAILED"
                schedule.last_error_message = str(exc)[:500]
                self.session.commit()
            raise
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def open_download(self, organization_id: str):
        schedule = self.get_schedule(organization_id)
        if not schedule.last_object_key:
            raise BackupNotAvailableError("Még nem készült letölthető biztonsági mentés.")
        stream = self.storage.open_stream(schedule.last_object_key)
        if stream is None:
            raise BackupNotAvailableError("A mentésfájl nem található az objektumtárban.")
        return schedule, stream

    def _write_archive(
        self,
        target: Path,
        *,
        organization_id: str,
        generated_at: datetime,
    ) -> None:
        organization = self.session.get(Organization, organization_id)
        if organization is None:
            raise ValueError("A szervezet nem található.")

        table_counts: dict[str, int] = {}
        redacted_columns: dict[str, list[str]] = {}
        included_files: list[dict[str, Any]] = []
        missing_files: list[dict[str, str]] = []

        with ZipFile(target, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
            for table in Base.metadata.sorted_tables:
                if table.name in EXCLUDED_TABLES:
                    continue
                if table.name == "organizations":
                    condition = table.c.id == organization_id
                elif "organization_id" in table.c:
                    condition = table.c.organization_id == organization_id
                else:
                    continue

                rows: list[dict[str, Any]] = []
                removed: set[str] = set()
                for source_row in self.session.execute(
                    select(table).where(condition)
                ).mappings():
                    row: dict[str, Any] = {}
                    plugin_secret = (
                        table.name == "plugin_settings"
                        and bool(source_row.get("is_secret"))
                    )
                    for key, value in source_row.items():
                        lowered = key.casefold()
                        if any(part in lowered for part in SENSITIVE_COLUMN_PARTS):
                            removed.add(key)
                            continue
                        if plugin_secret and key == "value":
                            row[key] = "[REDACTED]"
                            removed.add(key)
                            continue
                        row[key] = _json_value(value)
                    rows.append(row)
                table_counts[table.name] = len(rows)
                if removed:
                    redacted_columns[table.name] = sorted(removed)
                archive.writestr(
                    f"data/{table.name}.json",
                    json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"),
                )

            self._add_object_files(
                archive,
                organization_id=organization_id,
                table_name="documents",
                included_files=included_files,
                missing_files=missing_files,
            )
            self._add_object_files(
                archive,
                organization_id=organization_id,
                table_name="vrp_import_batches",
                included_files=included_files,
                missing_files=missing_files,
            )
            manifest = {
                "format": "ai-raktar-organization-backup",
                "format_version": BACKUP_FORMAT_VERSION,
                "generated_at": generated_at.isoformat(),
                "organization": {
                    "id": organization.id,
                    "name": organization.name,
                    "slug": organization.slug,
                },
                "table_counts": table_counts,
                "included_files": included_files,
                "missing_files": missing_files,
                "security": {
                    "excluded_tables": sorted(EXCLUDED_TABLES),
                    "redacted_columns": redacted_columns,
                    "note": (
                        "Jelszó-, MFA-, munkamenet-, API-token- és titkos "
                        "integrációs adatok nincsenek a letölthető mentésben."
                    ),
                },
            }
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )

    def _add_object_files(
        self,
        archive: ZipFile,
        *,
        organization_id: str,
        table_name: str,
        included_files: list[dict[str, Any]],
        missing_files: list[dict[str, str]],
    ) -> None:
        table = Base.metadata.tables.get(table_name)
        if table is None or "object_key" not in table.c:
            return
        columns = [table.c.id, table.c.object_key]
        filename_column = table.c.get("original_filename")
        if filename_column is not None:
            columns.append(filename_column)
        statement = select(*columns).where(table.c.organization_id == organization_id)
        for row in self.session.execute(statement).mappings():
            original = str(row.get("original_filename") or f"{row['id']}.bin")
            fallback_filename = f"{row['id']}.bin"
            archive_name = (
                f"files/{table_name}/{row['id']}/"
                f"{_safe_filename(original, fallback_filename)}"
            )
            stream = None
            try:
                stream = self.storage.open_stream(str(row["object_key"]))
                if stream is None:
                    raise FileNotFoundError(str(row["object_key"]))
                with archive.open(archive_name, "w") as target:
                    shutil.copyfileobj(stream, target, length=1024 * 1024)
                included_files.append(
                    {
                        "source_table": table_name,
                        "source_id": str(row["id"]),
                        "original_filename": original,
                        "archive_path": archive_name,
                    }
                )
            except (FileNotFoundError, OSError):
                missing_files.append(
                    {
                        "source_table": table_name,
                        "source_id": str(row["id"]),
                        "object_key": str(row["object_key"]),
                    }
                )
            finally:
                if stream is not None:
                    stream.close()
