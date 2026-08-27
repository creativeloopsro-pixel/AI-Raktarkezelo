from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from uuid import uuid4
from zipfile import BadZipFile, ZipFile, is_zipfile

from sqlalchemy import Date, DateTime, Numeric, Time, delete, insert, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import Base
from app.models import AuditLog, User, utc_now
from app.services.backups import BACKUP_FORMAT_VERSION, BackupService
from app.storage import ObjectStorage, get_object_storage

RESTORABLE_TABLE_NAMES = (
    "inbound_emails",
    "products",
    "documents",
    "external_product_mappings",
    "packaging_units",
    "review_tasks",
    "stock_balances",
    "stock_movements",
    "vrp_import_batches",
    "vrp_import_schedules",
    "document_pages",
    "document_processing_jobs",
    "inbound_email_attachments",
    "inventory_report_runs",
    "inventory_report_schedules",
    "inventory_sessions",
    "product_barcodes",
    "vrp_import_errors",
    "vrp_import_items",
    "ai_requests",
    "inventory_counts",
    "ai_results",
    "stock_corrections",
    "ai_tool_calls",
    "goods_receipt_drafts",
    "goods_receipt_items",
)
FILE_TABLE_NAMES = frozenset({"documents", "vrp_import_batches"})
PRESERVED_SECURITY_DATA = (
    "felhasználók és jelszavak",
    "szerepkörök és jogosultságok",
    "MFA és helyreállító kódok",
    "munkamenetek és API-tokenek",
    "AI API-kulcsok",
    "e-mail és plugin titkos beállítások",
    "biztonsági mentési ütemezés",
)


class BackupRestoreError(RuntimeError):
    code = "backup_restore_failed"


class BackupRestoreTooLargeError(BackupRestoreError):
    code = "backup_restore_too_large"


class InvalidBackupArchiveError(BackupRestoreError):
    code = "invalid_backup_archive"


class BackupOrganizationMismatchError(BackupRestoreError):
    code = "backup_organization_mismatch"


@dataclass
class ValidatedBackup:
    source_generated_at: datetime
    source_sha256: str
    rows: dict[str, list[dict[str, Any]]]
    included_files: list[dict[str, str]]


@dataclass
class BackupRestoreResult:
    restored_at: datetime
    source_filename: str
    source_generated_at: datetime
    source_sha256: str
    restored_tables: int
    restored_rows: int
    restored_files: int
    safety_backup_created_at: datetime
    preserved_security_data: list[str]


def _safe_archive_path(value: str) -> str:
    if "\\" in value:
        raise InvalidBackupArchiveError("A ZIP érvénytelen fájlútvonalat tartalmaz.")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise InvalidBackupArchiveError("A ZIP érvénytelen fájlútvonalat tartalmaz.")
    normalized = path.as_posix()
    if normalized != value or len(normalized) > 500:
        raise InvalidBackupArchiveError("A ZIP érvénytelen fájlútvonalat tartalmaz.")
    return normalized


def _safe_object_filename(value: str) -> str:
    leaf = PurePosixPath(value.replace("\\", "/")).name
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", leaf).strip(".-")
    return normalized[:180] or "file.bin"


def _database_value(column, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column.type, DateTime):
        if not isinstance(value, str):
            raise InvalidBackupArchiveError(
                f"A(z) {column.table.name}.{column.name} dátumértéke érvénytelen."
            )
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(column.type, Date):
        if not isinstance(value, str):
            raise InvalidBackupArchiveError(
                f"A(z) {column.table.name}.{column.name} dátumértéke érvénytelen."
            )
        return date.fromisoformat(value)
    if isinstance(column.type, Time):
        if not isinstance(value, str):
            raise InvalidBackupArchiveError(
                f"A(z) {column.table.name}.{column.name} időértéke érvénytelen."
            )
        return time.fromisoformat(value)
    if isinstance(column.type, Numeric):
        return Decimal(str(value))
    return value


class BackupRestoreService:
    def __init__(
        self,
        session: Session,
        *,
        storage: ObjectStorage | None = None,
        settings: Settings | None = None,
    ):
        self.session = session
        self.storage = storage or get_object_storage()
        self.settings = settings or get_settings()

    def save_upload(self, stream: BinaryIO) -> tuple[Path, str]:
        maximum = self.settings.backup_restore_max_mb * 1024 * 1024
        digest = hashlib.sha256()
        size = 0
        with tempfile.NamedTemporaryFile(
            prefix="ai-raktar-restore-",
            suffix=".zip",
            delete=False,
        ) as target:
            path = Path(target.name)
            try:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > maximum:
                        raise BackupRestoreTooLargeError(
                            "A mentésfájl meghaladja a visszaállítási méretkorlátot."
                        )
                    digest.update(chunk)
                    target.write(chunk)
            except Exception:
                path.unlink(missing_ok=True)
                raise
        if size == 0:
            path.unlink(missing_ok=True)
            raise InvalidBackupArchiveError("A feltöltött mentésfájl üres.")
        return path, digest.hexdigest()

    def restore(
        self,
        *,
        user: User,
        source_path: Path,
        source_filename: str,
        source_sha256: str,
        correlation_id: str,
    ) -> BackupRestoreResult:
        validated = self._validate(
            source_path,
            organization_id=user.organization_id,
            source_sha256=source_sha256,
        )

        safety_schedule = BackupService(
            self.session,
            storage=self.storage,
        ).generate_now(
            user=user,
            correlation_id=f"{correlation_id}:pre-restore",
        )
        if safety_schedule.last_run_at is None:
            raise BackupRestoreError(
                "A visszaállítás előtti biztonsági pillanatkép nem készült el."
            )

        staged_object_keys: list[str] = []
        restored_at = utc_now()
        restore_id = str(uuid4())
        try:
            with ZipFile(source_path) as archive:
                staged_map = self._stage_files(
                    archive,
                    validated,
                    organization_id=user.organization_id,
                    restore_id=restore_id,
                    staged_object_keys=staged_object_keys,
                )
            old_object_keys = self._current_object_keys(user.organization_id)
            self._replace_rows(
                validated.rows,
                organization_id=user.organization_id,
                staged_object_keys=staged_map,
            )
            restored_rows = sum(len(rows) for rows in validated.rows.values())
            self.session.add(
                AuditLog(
                    organization_id=user.organization_id,
                    actor_id=user.id,
                    action="backup.restored",
                    entity_type="backup",
                    entity_id=user.organization_id,
                    correlation_id=correlation_id,
                    details={
                        "source_filename": Path(source_filename).name[:255],
                        "source_generated_at": validated.source_generated_at.isoformat(),
                        "source_sha256": validated.source_sha256,
                        "restored_tables": len(validated.rows),
                        "restored_rows": restored_rows,
                        "restored_files": len(staged_map),
                        "preserved_security_data": list(PRESERVED_SECURITY_DATA),
                        "safety_backup_created_at": (
                            safety_schedule.last_run_at.isoformat()
                        ),
                    },
                )
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            for object_key in staged_object_keys:
                with suppress(Exception):
                    self.storage.delete(object_key)
            raise

        for object_key in old_object_keys - set(staged_object_keys):
            with suppress(Exception):
                self.storage.delete(object_key)

        return BackupRestoreResult(
            restored_at=restored_at,
            source_filename=Path(source_filename).name[:255]
            or "ai-raktar-biztonsagi-mentes.zip",
            source_generated_at=validated.source_generated_at,
            source_sha256=validated.source_sha256,
            restored_tables=len(validated.rows),
            restored_rows=sum(len(rows) for rows in validated.rows.values()),
            restored_files=len(staged_object_keys),
            safety_backup_created_at=safety_schedule.last_run_at,
            preserved_security_data=list(PRESERVED_SECURITY_DATA),
        )

    def _validate(
        self,
        source_path: Path,
        *,
        organization_id: str,
        source_sha256: str,
    ) -> ValidatedBackup:
        if not is_zipfile(source_path):
            raise InvalidBackupArchiveError(
                "A feltöltött fájl nem érvényes AI Raktár ZIP-mentés."
            )
        try:
            with ZipFile(source_path) as archive:
                infos = archive.infolist()
                if len(infos) > self.settings.backup_restore_max_entries:
                    raise BackupRestoreTooLargeError(
                        "A mentés túl sok ZIP-bejegyzést tartalmaz."
                    )
                names: set[str] = set()
                total_uncompressed = 0
                for info in infos:
                    name = _safe_archive_path(info.filename)
                    if name in names:
                        raise InvalidBackupArchiveError(
                            "A ZIP ismétlődő fájlneveket tartalmaz."
                        )
                    names.add(name)
                    if info.flag_bits & 0x1:
                        raise InvalidBackupArchiveError(
                            "Titkosított ZIP-bejegyzés nem állítható vissza."
                        )
                    total_uncompressed += info.file_size
                    if (
                        info.file_size > 10 * 1024 * 1024
                        and info.compress_size > 0
                        and info.file_size / info.compress_size > 500
                    ):
                        raise InvalidBackupArchiveError(
                            "A ZIP veszélyes tömörítési arányt tartalmaz."
                        )
                maximum_uncompressed = (
                    self.settings.backup_restore_max_uncompressed_mb * 1024 * 1024
                )
                if total_uncompressed > maximum_uncompressed:
                    raise BackupRestoreTooLargeError(
                        "A kicsomagolt mentés meghaladná a méretkorlátot."
                    )

                manifest = self._read_json(archive, "manifest.json")
                if not isinstance(manifest, dict):
                    raise InvalidBackupArchiveError("A mentési manifest érvénytelen.")
                if manifest.get("format") != "ai-raktar-organization-backup":
                    raise InvalidBackupArchiveError(
                        "A ZIP nem AI Raktár szervezeti mentés."
                    )
                if str(manifest.get("format_version")) != BACKUP_FORMAT_VERSION:
                    raise InvalidBackupArchiveError(
                        "A mentés formátumverziója nem támogatott."
                    )
                manifest_organization = manifest.get("organization")
                if (
                    not isinstance(manifest_organization, dict)
                    or manifest_organization.get("id") != organization_id
                ):
                    raise BackupOrganizationMismatchError(
                        "A mentés másik szervezethez tartozik."
                    )
                generated_at_value = manifest.get("generated_at")
                if not isinstance(generated_at_value, str):
                    raise InvalidBackupArchiveError(
                        "A mentés létrehozási időpontja hiányzik."
                    )
                source_generated_at = datetime.fromisoformat(
                    generated_at_value.replace("Z", "+00:00")
                )
                table_counts = manifest.get("table_counts")
                if not isinstance(table_counts, dict):
                    raise InvalidBackupArchiveError(
                        "A mentés táblajegyzéke hiányzik."
                    )

                rows: dict[str, list[dict[str, Any]]] = {}
                total_rows = 0
                for table_name in RESTORABLE_TABLE_NAMES:
                    entry_name = f"data/{table_name}.json"
                    if entry_name not in names:
                        raise InvalidBackupArchiveError(
                            f"A mentésből hiányzik: {entry_name}."
                        )
                    table_rows = self._read_json(archive, entry_name)
                    if not isinstance(table_rows, list) or any(
                        not isinstance(row, dict) for row in table_rows
                    ):
                        raise InvalidBackupArchiveError(
                            f"A(z) {table_name} mentési adatai érvénytelenek."
                        )
                    if table_counts.get(table_name) != len(table_rows):
                        raise InvalidBackupArchiveError(
                            f"A(z) {table_name} sorszáma nem egyezik a manifesttel."
                        )
                    total_rows += len(table_rows)
                    if total_rows > 500_000:
                        raise BackupRestoreTooLargeError(
                            "A mentés túl sok adatbázisrekordot tartalmaz."
                        )
                    rows[table_name] = self._validate_rows(
                        table_name,
                        table_rows,
                        organization_id=organization_id,
                    )

                included_files = manifest.get("included_files", [])
                if not isinstance(included_files, list):
                    raise InvalidBackupArchiveError(
                        "A mentés fájljegyzéke érvénytelen."
                    )
                normalized_files: list[dict[str, str]] = []
                referenced_paths: set[str] = set()
                referenced_sources: set[tuple[str, str]] = set()
                for item in included_files:
                    if not isinstance(item, dict):
                        raise InvalidBackupArchiveError(
                            "A mentés fájljegyzéke érvénytelen."
                        )
                    table_name = item.get("source_table")
                    source_id = item.get("source_id")
                    archive_path = item.get("archive_path")
                    original_filename = item.get("original_filename")
                    if (
                        table_name not in FILE_TABLE_NAMES
                        or not isinstance(source_id, str)
                        or not isinstance(archive_path, str)
                        or not isinstance(original_filename, str)
                    ):
                        raise InvalidBackupArchiveError(
                            "A mentés fájljegyzéke ismeretlen elemet tartalmaz."
                        )
                    archive_path = _safe_archive_path(archive_path)
                    if not archive_path.startswith(f"files/{table_name}/"):
                        raise InvalidBackupArchiveError(
                            "A mentés egyik fájlútvonala érvénytelen."
                        )
                    source_key = (table_name, source_id)
                    if (
                        archive_path not in names
                        or archive_path in referenced_paths
                        or source_key in referenced_sources
                    ):
                        raise InvalidBackupArchiveError(
                            "A mentés fájljegyzéke hiányos vagy ismétlődő."
                        )
                    if not any(
                        str(row.get("id")) == source_id for row in rows[table_name]
                    ):
                        raise InvalidBackupArchiveError(
                            "A mentés fájljegyzéke nem létező rekordra hivatkozik."
                        )
                    referenced_paths.add(archive_path)
                    referenced_sources.add(source_key)
                    normalized_files.append(
                        {
                            "source_table": table_name,
                            "source_id": source_id,
                            "archive_path": archive_path,
                            "original_filename": original_filename,
                        }
                    )
                actual_file_paths = {
                    name
                    for name in names
                    if name.startswith("files/") and not name.endswith("/")
                }
                if actual_file_paths != referenced_paths:
                    raise InvalidBackupArchiveError(
                        "A ZIP fájltartalma nem egyezik a manifesttel."
                    )
                return ValidatedBackup(
                    source_generated_at=source_generated_at,
                    source_sha256=source_sha256,
                    rows=rows,
                    included_files=normalized_files,
                )
        except (BadZipFile, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            if isinstance(exc, BackupRestoreError):
                raise
            raise InvalidBackupArchiveError(
                "A mentés ZIP- vagy JSON-tartalma sérült."
            ) from exc

    def _read_json(self, archive: ZipFile, name: str) -> Any:
        try:
            info = archive.getinfo(name)
        except KeyError as exc:
            raise InvalidBackupArchiveError(f"A mentésből hiányzik: {name}.") from exc
        if info.file_size > 256 * 1024 * 1024:
            raise BackupRestoreTooLargeError(
                f"A(z) {name} mentési adatállomány túl nagy."
            )
        with archive.open(info) as source:
            return json.load(source)

    def _validate_rows(
        self,
        table_name: str,
        source_rows: list[dict[str, Any]],
        *,
        organization_id: str,
    ) -> list[dict[str, Any]]:
        table = Base.metadata.tables[table_name]
        allowed_columns = set(table.c.keys())
        converted_rows: list[dict[str, Any]] = []
        primary_keys: set[tuple[Any, ...]] = set()
        for source_row in source_rows:
            unknown = set(source_row) - allowed_columns
            if unknown:
                raise InvalidBackupArchiveError(
                    f"A(z) {table_name} ismeretlen oszlopot tartalmaz."
                )
            if source_row.get("organization_id") != organization_id:
                raise BackupOrganizationMismatchError(
                    f"A(z) {table_name} másik szervezet rekordját tartalmazza."
                )
            converted: dict[str, Any] = {}
            for key, value in source_row.items():
                converted[key] = _database_value(table.c[key], value)
            converted["organization_id"] = organization_id
            primary_key = tuple(converted.get(column.name) for column in table.primary_key)
            if None in primary_key or primary_key in primary_keys:
                raise InvalidBackupArchiveError(
                    f"A(z) {table_name} hiányzó vagy ismétlődő elsődleges kulcsot tartalmaz."
                )
            primary_keys.add(primary_key)
            converted_rows.append(converted)
        return converted_rows

    def _stage_files(
        self,
        archive: ZipFile,
        validated: ValidatedBackup,
        *,
        organization_id: str,
        restore_id: str,
        staged_object_keys: list[str],
    ) -> dict[tuple[str, str], str]:
        rows_by_source = {
            (table_name, str(row["id"])): row
            for table_name in FILE_TABLE_NAMES
            for row in validated.rows[table_name]
        }
        staged_map: dict[tuple[str, str], str] = {}
        for item in validated.included_files:
            source_key = (item["source_table"], item["source_id"])
            row = rows_by_source[source_key]
            filename = _safe_object_filename(item["original_filename"])
            object_key = (
                f"restores/{organization_id}/{restore_id}/"
                f"{item['source_table']}/{item['source_id']}/{filename}"
            )
            with tempfile.NamedTemporaryFile(
                prefix="ai-raktar-restore-object-",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                try:
                    with archive.open(item["archive_path"]) as source:
                        shutil.copyfileobj(source, temporary, length=1024 * 1024)
                    temporary.flush()
                    staged_object_keys.append(object_key)
                    self.storage.put_file(
                        temporary_path,
                        object_key,
                        str(row.get("content_type") or "application/octet-stream"),
                    )
                finally:
                    temporary_path.unlink(missing_ok=True)
            staged_map[source_key] = object_key
        return staged_map

    def _current_object_keys(self, organization_id: str) -> set[str]:
        keys: set[str] = set()
        for table_name in FILE_TABLE_NAMES:
            table = Base.metadata.tables[table_name]
            keys.update(
                str(value)
                for value in self.session.scalars(
                    select(table.c.object_key).where(
                        table.c.organization_id == organization_id
                    )
                )
                if value
            )
        return keys

    def _replace_rows(
        self,
        rows: dict[str, list[dict[str, Any]]],
        *,
        organization_id: str,
        staged_object_keys: dict[tuple[str, str], str],
    ) -> None:
        tables = [Base.metadata.tables[name] for name in RESTORABLE_TABLE_NAMES]
        current_user_ids = set(
            self.session.scalars(
                select(User.id).where(User.organization_id == organization_id)
            )
        )
        for table in reversed(tables):
            self.session.execute(
                delete(table).where(table.c.organization_id == organization_id)
            )
        self.session.flush()

        for table in tables:
            prepared_rows: list[dict[str, Any]] = []
            user_columns = {
                foreign_key.parent.name: foreign_key.parent
                for foreign_key in table.foreign_keys
                if foreign_key.column.table.name == "users"
            }
            for source_row in rows[table.name]:
                row = dict(source_row)
                source_key = (table.name, str(row.get("id")))
                if source_key in staged_object_keys:
                    row["object_key"] = staged_object_keys[source_key]
                for column_name, column in user_columns.items():
                    value = row.get(column_name)
                    if value is not None and value not in current_user_ids:
                        if not column.nullable:
                            raise InvalidBackupArchiveError(
                                f"A(z) {table.name} egy már nem létező felhasználóra hivatkozik."
                            )
                        row[column_name] = None
                prepared_rows.append(row)
            if prepared_rows:
                self.session.execute(insert(table).values(prepared_rows))
        self.session.flush()
