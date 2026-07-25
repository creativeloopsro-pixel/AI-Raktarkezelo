from __future__ import annotations

from secrets import token_urlsafe
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.models import (
    AuditLog,
    Organization,
    OutboxEvent,
    Plugin,
    PluginJob,
    PluginPermission,
    PluginSetting,
    PluginVersion,
    User,
    utc_now,
)
from app.plugins.manifest import (
    BUILTIN_PLUGIN_MANIFESTS,
    DEFAULT_ENABLED_BUILTINS,
    PluginManifest,
)
from app.plugins.registry import PluginRegistry, plugin_registry
from app.security import hash_password


class PluginServiceError(Exception):
    code = "plugin_error"


class PluginNotFoundError(PluginServiceError):
    code = "plugin_not_found"


class PluginManifestError(PluginServiceError):
    code = "invalid_plugin_manifest"


class PluginApiVersionError(PluginServiceError):
    code = "unsupported_plugin_api_version"


class PluginHandlerMissingError(PluginServiceError):
    code = "plugin_handler_missing"


class PluginPermissionError(PluginServiceError):
    code = "invalid_plugin_permissions"


class PluginEnableError(PluginServiceError):
    code = "plugin_cannot_be_enabled"


class PluginSettingError(PluginServiceError):
    code = "invalid_plugin_setting"


class BuiltinPluginProtectedError(PluginServiceError):
    code = "builtin_plugin_protected"


class PluginService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        registry: PluginRegistry | None = None,
    ):
        self.session = session
        self.settings = settings or get_settings()
        self.registry = registry or plugin_registry

    def ensure_builtin_plugins(self, organization_id: str) -> list[Plugin]:
        installed: list[Plugin] = []
        for manifest in BUILTIN_PLUGIN_MANIFESTS:
            plugin = self._install_manifest(
                organization_id=organization_id,
                manifest=manifest,
                installed_by=None,
                builtin=True,
                enable_by_default=manifest.id in DEFAULT_ENABLED_BUILTINS,
            )
            installed.append(plugin)
        self.session.commit()
        return installed

    def ensure_all_builtin_plugins(self) -> None:
        organization_ids = list(self.session.scalars(select(Organization.id)))
        for organization_id in organization_ids:
            self.ensure_builtin_plugins(organization_id)

    def install_manifest(
        self,
        *,
        user: User,
        manifest_payload: dict[str, Any],
        correlation_id: str,
    ) -> Plugin:
        try:
            manifest = PluginManifest.model_validate(manifest_payload)
        except ValidationError as exc:
            raise PluginManifestError from exc
        if manifest.api_version != self.settings.plugin_api_version:
            raise PluginApiVersionError
        if manifest.subscribes and not self.registry.supports_manifest(
            manifest.id, manifest.subscribes
        ):
            raise PluginHandlerMissingError
        existing = self.session.scalar(
            select(Plugin).where(
                Plugin.organization_id == user.organization_id,
                Plugin.plugin_key == manifest.id,
            )
        )
        if existing is not None and existing.is_builtin:
            raise BuiltinPluginProtectedError

        plugin = self._install_manifest(
            organization_id=user.organization_id,
            manifest=manifest,
            installed_by=user.id,
            builtin=False,
            enable_by_default=False,
        )
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="plugin.installed",
                entity_type="plugin",
                entity_id=plugin.id,
                correlation_id=correlation_id,
                details={
                    "plugin_key": plugin.plugin_key,
                    "version": manifest.version,
                    "permissions": manifest.permissions,
                },
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=user.organization_id,
                event_type="plugin.installed",
                aggregate_type="plugin",
                aggregate_id=plugin.id,
                payload={
                    "plugin_id": plugin.plugin_key,
                    "version": manifest.version,
                    "correlation_id": correlation_id,
                },
            )
        )
        self.session.commit()
        self.session.expire(plugin)
        return self.get_plugin(user.organization_id, plugin.id)

    def list_plugins(self, organization_id: str) -> list[Plugin]:
        self.ensure_builtin_plugins(organization_id)
        return list(
            self.session.scalars(
                self._plugin_query()
                .where(Plugin.organization_id == organization_id)
                .order_by(Plugin.is_builtin.desc(), Plugin.name)
            ).unique()
        )

    def get_plugin(self, organization_id: str, plugin_id: str) -> Plugin:
        plugin = self.session.scalar(
            self._plugin_query().where(
                Plugin.id == plugin_id,
                Plugin.organization_id == organization_id,
            )
        )
        if plugin is None:
            raise PluginNotFoundError
        return plugin

    def get_by_key(self, organization_id: str, plugin_key: str) -> Plugin:
        plugin = self.session.scalar(
            self._plugin_query().where(
                Plugin.plugin_key == plugin_key,
                Plugin.organization_id == organization_id,
            )
        )
        if plugin is None:
            raise PluginNotFoundError
        return plugin

    def set_permissions(
        self,
        *,
        user: User,
        plugin_id: str,
        granted_permissions: list[str],
        correlation_id: str,
    ) -> Plugin:
        plugin = self.get_plugin(user.organization_id, plugin_id)
        declared = {permission.permission for permission in plugin.permissions}
        requested = set(granted_permissions)
        if not requested.issubset(declared):
            raise PluginPermissionError
        now = utc_now()
        for permission in plugin.permissions:
            should_grant = permission.permission in requested
            permission.granted = should_grant
            permission.granted_by = user.id if should_grant else None
            permission.granted_at = now if should_grant else None
        if plugin.status == "ENABLED" and requested != declared:
            plugin.status = "DISABLED"
            plugin.disabled_at = now
        self._audit_configuration(
            plugin=plugin,
            user=user,
            action="plugin.permissions_updated",
            correlation_id=correlation_id,
            details={"granted_permissions": sorted(requested)},
        )
        self.session.commit()
        return self.get_plugin(user.organization_id, plugin.id)

    def enable(
        self, *, user: User, plugin_id: str, correlation_id: str
    ) -> Plugin:
        plugin = self.get_plugin(user.organization_id, plugin_id)
        manifest = self.manifest_for(plugin)
        if manifest.api_version != self.settings.plugin_api_version:
            raise PluginApiVersionError
        granted = {
            permission.permission
            for permission in plugin.permissions
            if permission.granted
        }
        if not set(manifest.permissions).issubset(granted):
            raise PluginEnableError
        if manifest.subscribes and not self.registry.supports_manifest(
            plugin.plugin_key, manifest.subscribes
        ):
            raise PluginHandlerMissingError
        plugin.status = "ENABLED"
        plugin.enabled_at = utc_now()
        plugin.disabled_at = None
        self._audit_configuration(
            plugin=plugin,
            user=user,
            action="plugin.enabled",
            correlation_id=correlation_id,
            details={"version": plugin.active_version},
        )
        self.session.commit()
        return self.get_plugin(user.organization_id, plugin.id)

    def disable(
        self, *, user: User, plugin_id: str, correlation_id: str
    ) -> Plugin:
        plugin = self.get_plugin(user.organization_id, plugin_id)
        plugin.status = "DISABLED"
        plugin.disabled_at = utc_now()
        self._audit_configuration(
            plugin=plugin,
            user=user,
            action="plugin.disabled",
            correlation_id=correlation_id,
            details={"version": plugin.active_version},
        )
        self.session.commit()
        return self.get_plugin(user.organization_id, plugin.id)

    def update_settings(
        self,
        *,
        user: User,
        plugin_id: str,
        values: dict[str, Any],
        correlation_id: str,
    ) -> Plugin:
        plugin = self.get_plugin(user.organization_id, plugin_id)
        manifest = self.manifest_for(plugin)
        self._validate_settings(manifest, values)
        properties = manifest.settings_schema.get("properties", {})
        existing = {setting.setting_key: setting for setting in plugin.settings}
        for key, value in values.items():
            is_secret = bool(properties.get(key, {}).get("writeOnly", False))
            setting = existing.get(key)
            if setting is None:
                self.session.add(
                    PluginSetting(
                        organization_id=user.organization_id,
                        plugin_id=plugin.id,
                        setting_key=key,
                        value=value,
                        is_secret=is_secret,
                        updated_by=user.id,
                    )
                )
            else:
                setting.value = value
                setting.is_secret = is_secret
                setting.updated_by = user.id
        self._audit_configuration(
            plugin=plugin,
            user=user,
            action="plugin.settings_updated",
            correlation_id=correlation_id,
            details={"setting_keys": sorted(values)},
        )
        self.session.commit()
        self.session.expire(plugin)
        return self.get_plugin(user.organization_id, plugin.id)

    def list_jobs(
        self,
        organization_id: str,
        *,
        plugin_id: str | None = None,
        limit: int = 100,
    ) -> list[PluginJob]:
        statement = select(PluginJob).where(
            PluginJob.organization_id == organization_id
        )
        if plugin_id:
            statement = statement.where(PluginJob.plugin_id == plugin_id)
        return list(
            self.session.scalars(
                statement.order_by(PluginJob.created_at.desc()).limit(limit)
            )
        )

    def job_counts(self, organization_id: str) -> dict[str, int]:
        rows = self.session.execute(
            select(PluginJob.status, func.count(PluginJob.id))
            .where(PluginJob.organization_id == organization_id)
            .group_by(PluginJob.status)
        )
        return {status: int(count) for status, count in rows}

    def manifest_for(self, plugin: Plugin) -> PluginManifest:
        version = next(
            (
                candidate
                for candidate in plugin.versions
                if candidate.version == plugin.active_version
            ),
            None,
        )
        if version is None:
            version = self.session.scalar(
                select(PluginVersion).where(
                    PluginVersion.plugin_id == plugin.id,
                    PluginVersion.version == plugin.active_version,
                )
            )
        if version is None:
            raise PluginManifestError
        try:
            return PluginManifest.model_validate(version.manifest)
        except ValidationError as exc:
            raise PluginManifestError from exc

    def _install_manifest(
        self,
        *,
        organization_id: str,
        manifest: PluginManifest,
        installed_by: str | None,
        builtin: bool,
        enable_by_default: bool,
    ) -> Plugin:
        if manifest.api_version != self.settings.plugin_api_version:
            raise PluginApiVersionError
        plugin = self.session.scalar(
            select(Plugin).where(
                Plugin.organization_id == organization_id,
                Plugin.plugin_key == manifest.id,
            )
        )
        initial_install = plugin is None
        if plugin is None:
            service_user = self._service_user(organization_id, manifest)
            plugin = Plugin(
                organization_id=organization_id,
                plugin_key=manifest.id,
                name=manifest.name,
                description=manifest.description,
                status="ENABLED" if enable_by_default else "DISABLED",
                active_version=manifest.version,
                is_builtin=builtin,
                service_user_id=service_user.id,
                installed_by=installed_by,
                enabled_at=utc_now() if enable_by_default else None,
            )
            self.session.add(plugin)
            self.session.flush()
        else:
            plugin.name = manifest.name
            plugin.description = manifest.description
            plugin.active_version = manifest.version
            plugin.is_builtin = plugin.is_builtin or builtin

        version_exists = self.session.scalar(
            select(PluginVersion.id).where(
                PluginVersion.plugin_id == plugin.id,
                PluginVersion.version == manifest.version,
            )
        )
        if version_exists is None:
            self.session.add(
                PluginVersion(
                    organization_id=organization_id,
                    plugin_id=plugin.id,
                    version=manifest.version,
                    api_version=manifest.api_version,
                    manifest=manifest.model_dump(mode="json"),
                    installed_by=installed_by,
                )
            )

        existing_permissions = {
            permission.permission: permission
            for permission in self.session.scalars(
                select(PluginPermission).where(
                    PluginPermission.plugin_id == plugin.id
                )
            )
        }
        for permission_name in manifest.permissions:
            if permission_name not in existing_permissions:
                granted = builtin and initial_install
                self.session.add(
                    PluginPermission(
                        organization_id=organization_id,
                        plugin_id=plugin.id,
                        permission=permission_name,
                        granted=granted,
                        granted_by=installed_by if granted else None,
                        granted_at=utc_now() if granted else None,
                    )
                )
        removed_permissions = set(existing_permissions) - set(manifest.permissions)
        for permission_name in removed_permissions:
            self.session.delete(existing_permissions[permission_name])
        if not initial_install and any(
            permission not in existing_permissions
            for permission in manifest.permissions
        ):
            plugin.status = "DISABLED"
            plugin.disabled_at = utc_now()

        properties = manifest.settings_schema.get("properties", {})
        existing_setting_keys = set(
            self.session.scalars(
                select(PluginSetting.setting_key).where(
                    PluginSetting.plugin_id == plugin.id
                )
            )
        )
        for key, schema in properties.items():
            if key not in existing_setting_keys and "default" in schema:
                self.session.add(
                    PluginSetting(
                        organization_id=organization_id,
                        plugin_id=plugin.id,
                        setting_key=key,
                        value=schema["default"],
                        is_secret=bool(schema.get("writeOnly", False)),
                    )
                )
        self.session.flush()
        return plugin

    def _service_user(
        self, organization_id: str, manifest: PluginManifest
    ) -> User:
        email = f"plugin+{manifest.id}@service.invalid"
        service_user = self.session.scalar(
            select(User).where(
                User.organization_id == organization_id,
                User.email == email,
            )
        )
        if service_user is None:
            service_user = User(
                organization_id=organization_id,
                email=email,
                full_name=f"Plugin: {manifest.name}",
                password_hash=hash_password(token_urlsafe(48)),
                role="plugin_service",
                is_active=False,
            )
            self.session.add(service_user)
            self.session.flush()
        return service_user

    def _validate_settings(
        self, manifest: PluginManifest, values: dict[str, Any]
    ) -> None:
        schema = manifest.settings_schema
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = set(values) - set(properties)
            if unknown:
                raise PluginSettingError
        python_types = {
            "boolean": bool,
            "string": str,
            "integer": int,
            "number": (int, float),
            "object": dict,
            "array": list,
        }
        for key, value in values.items():
            expected_name = properties.get(key, {}).get("type")
            expected = python_types.get(expected_name)
            if expected is not None and not isinstance(value, expected):
                raise PluginSettingError

    def _audit_configuration(
        self,
        *,
        plugin: Plugin,
        user: User,
        action: str,
        correlation_id: str,
        details: dict[str, Any],
    ) -> None:
        self.session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action=action,
                entity_type="plugin",
                entity_id=plugin.id,
                correlation_id=correlation_id,
                details={"plugin_key": plugin.plugin_key, **details},
            )
        )
        self.session.add(
            OutboxEvent(
                organization_id=user.organization_id,
                event_type=action,
                aggregate_type="plugin",
                aggregate_id=plugin.id,
                payload={
                    "plugin_id": plugin.plugin_key,
                    **details,
                    "correlation_id": correlation_id,
                },
            )
        )

    @staticmethod
    def _plugin_query():
        return select(Plugin).options(
            selectinload(Plugin.versions),
            selectinload(Plugin.permissions),
            selectinload(Plugin.settings),
            selectinload(Plugin.service_user),
        )
