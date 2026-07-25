from __future__ import annotations

from datetime import UTC, datetime
from secrets import token_urlsafe

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import (
    ApiToken,
    AuditLog,
    Permission,
    Role,
    RolePermission,
    User,
    UserMfaMethod,
    UserRole,
    utc_now,
)
from app.security import api_token_hash, hash_password

PERMISSION_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    ("system.admin", "Rendszeradminisztráció", "identity"),
    ("users.read", "Felhasználók megtekintése", "identity"),
    ("users.write", "Felhasználók kezelése", "identity"),
    ("roles.read", "Szerepkörök megtekintése", "identity"),
    ("roles.write", "Szerepkörök kezelése", "identity"),
    ("sessions.read", "Munkamenetek megtekintése", "identity"),
    ("sessions.revoke", "Munkamenetek visszavonása", "identity"),
    ("tokens.read", "API-tokenek megtekintése", "identity"),
    ("tokens.create", "API-tokenek létrehozása", "identity"),
    ("tokens.revoke", "API-tokenek visszavonása", "identity"),
    ("products.read", "Termékek megtekintése", "catalog"),
    ("products.write", "Termékek kezelése", "catalog"),
    ("stock.read", "Készlet megtekintése", "inventory"),
    ("stock.receive", "Bevételezés", "inventory"),
    ("stock.correct", "Készletkorrekció", "inventory"),
    ("stock.reverse", "Készletmozgás visszavonása", "inventory"),
    ("inventory.count", "Kézi leltár", "inventory"),
    ("inventory.approve", "Leltár jóváhagyása", "inventory"),
    ("documents.read", "Dokumentumok megtekintése", "documents"),
    ("documents.upload", "Dokumentumfeltöltés", "documents"),
    ("documents.process", "Dokumentumfeldolgozás", "documents"),
    ("receipts.read", "Bevételezési tervezetek megtekintése", "documents"),
    ("receipts.confirm", "Bevételezés jóváhagyása", "documents"),
    ("reviews.read", "Ellenőrzések megtekintése", "reviews"),
    ("reviews.resolve", "Ellenőrzések lezárása", "reviews"),
    ("vrp.read", "VRP-importok megtekintése", "vrp"),
    ("vrp.upload", "VRP-fájlok feltöltése", "vrp"),
    ("vrp.process", "VRP-importok feldolgozása", "vrp"),
    ("vrp.settings", "VRP-beállítások kezelése", "vrp"),
    ("email.read", "E-mailes beérkezés megtekintése", "email"),
    ("email.manage", "E-mailes beérkezés kezelése", "email"),
    ("plugins.read", "Pluginok megtekintése", "plugins"),
    ("plugins.manage", "Pluginok kezelése", "plugins"),
    ("reports.read", "Riportok megtekintése", "reports"),
    ("reports.generate", "Riportok létrehozása", "reports"),
    ("notifications.read", "Értesítések megtekintése", "system"),
    ("settings.read", "Beállítások megtekintése", "system"),
    ("settings.write", "Beállítások kezelése", "system"),
)

ALL_PERMISSION_CODES = frozenset(code for code, _, _ in PERMISSION_DEFINITIONS)
BUILTIN_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": ALL_PERMISSION_CODES,
    "manager": frozenset(
        {
            "products.read",
            "products.write",
            "stock.read",
            "stock.receive",
            "stock.correct",
            "stock.reverse",
            "inventory.count",
            "inventory.approve",
            "documents.read",
            "documents.upload",
            "documents.process",
            "receipts.read",
            "receipts.confirm",
            "reviews.read",
            "reviews.resolve",
            "vrp.read",
            "vrp.upload",
            "vrp.process",
            "reports.read",
            "reports.generate",
            "notifications.read",
            "sessions.read",
        }
    ),
    "warehouse": frozenset(
        {
            "products.read",
            "stock.read",
            "stock.receive",
            "inventory.count",
            "documents.read",
            "documents.upload",
            "documents.process",
            "receipts.read",
            "receipts.confirm",
            "reviews.read",
            "vrp.read",
            "vrp.upload",
        }
    ),
    "viewer": frozenset(
        {
            "products.read",
            "stock.read",
            "documents.read",
            "receipts.read",
            "reviews.read",
            "vrp.read",
            "reports.read",
            "notifications.read",
        }
    ),
    "service": frozenset({"products.read", "stock.read", "documents.read"}),
}
BUILTIN_ROLE_NAMES = {
    "admin": "Tulajdonos / Admin",
    "manager": "Üzletvezető",
    "warehouse": "Eladó / Raktári felhasználó",
    "viewer": "Ellenőr / Megtekintő",
    "service": "Plugin szolgáltatásfiók",
}


class IdentityError(Exception):
    code = "identity_error"


class IdentityNotFoundError(IdentityError):
    code = "identity_not_found"


class IdentityConflictError(IdentityError):
    code = "identity_conflict"


class IdentityValidationError(IdentityError):
    code = "identity_validation"


def effective_role_slugs(session: Session, user: User) -> set[str]:
    assigned = set(
        session.scalars(
            select(Role.slug)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.organization_id == user.organization_id,
                UserRole.user_id == user.id,
            )
        )
    )
    if assigned:
        return assigned
    legacy = (
        "service"
        if user.role in {"plugin", "plugin_service"}
        else user.role
    )
    return {legacy}


def effective_permissions(session: Session, user: User) -> set[str]:
    permissions = set(
        session.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(
                UserRole.organization_id == user.organization_id,
                UserRole.user_id == user.id,
                RolePermission.organization_id == user.organization_id,
            )
        )
    )
    if permissions:
        return permissions
    result: set[str] = set()
    for role_slug in effective_role_slugs(session, user):
        result.update(BUILTIN_ROLE_PERMISSIONS.get(role_slug, frozenset()))
    return result


class IdentityService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
    ):
        self.session = session
        self.settings = settings or get_settings()

    def ensure_organization(self, organization_id: str) -> None:
        permissions = {
            permission.code: permission
            for permission in self.session.scalars(select(Permission))
        }
        for code, name, category in PERMISSION_DEFINITIONS:
            if code not in permissions:
                permission = Permission(
                    code=code,
                    name=name,
                    description="",
                    category=category,
                )
                self.session.add(permission)
                permissions[code] = permission
        self.session.flush()

        roles = {
            role.slug: role
            for role in self.session.scalars(
                select(Role).where(Role.organization_id == organization_id)
            )
        }
        for slug, permission_codes in BUILTIN_ROLE_PERMISSIONS.items():
            role = roles.get(slug)
            created = role is None
            if role is None:
                role = Role(
                    organization_id=organization_id,
                    name=BUILTIN_ROLE_NAMES[slug],
                    slug=slug,
                    description="Beépített architektúra-szerepkör.",
                    is_system=True,
                )
                self.session.add(role)
                self.session.flush()
                roles[slug] = role
            if created:
                for code in permission_codes:
                    self.session.add(
                        RolePermission(
                            organization_id=organization_id,
                            role_id=role.id,
                            permission_id=permissions[code].id,
                        )
                    )

        self.session.flush()
        users = self.session.scalars(
            select(User).where(User.organization_id == organization_id)
        )
        for user in users:
            assigned_slugs = set(
                self.session.scalars(
                    select(Role.slug)
                    .join(UserRole, UserRole.role_id == Role.id)
                    .where(
                        UserRole.organization_id == organization_id,
                        UserRole.user_id == user.id,
                    )
                )
            )
            is_plugin_service = user.role in {"plugin", "plugin_service"}
            if is_plugin_service and assigned_slugs != {"service"}:
                self.session.execute(
                    delete(UserRole).where(
                        UserRole.organization_id == organization_id,
                        UserRole.user_id == user.id,
                    )
                )
                self.session.add(
                    UserRole(
                        organization_id=organization_id,
                        user_id=user.id,
                        role_id=roles["service"].id,
                    )
                )
                continue
            if not assigned_slugs:
                legacy_slug = (
                    "service"
                    if is_plugin_service
                    else user.role
                )
                role = roles.get(legacy_slug) or roles["warehouse"]
                self.session.add(
                    UserRole(
                        organization_id=organization_id,
                        user_id=user.id,
                        role_id=role.id,
                    )
                )

    def list_permissions(self) -> list[Permission]:
        return list(
            self.session.scalars(
                select(Permission).order_by(Permission.category, Permission.code)
            )
        )

    def list_roles(self, organization_id: str) -> list[Role]:
        return list(
            self.session.scalars(
                select(Role)
                .where(Role.organization_id == organization_id)
                .order_by(Role.is_system.desc(), Role.name)
            )
        )

    def role_permission_codes(self, role_id: str) -> list[str]:
        return list(
            self.session.scalars(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role_id)
                .order_by(Permission.code)
            )
        )

    def get_role(self, organization_id: str, role_id: str) -> Role:
        role = self.session.scalar(
            select(Role).where(
                Role.id == role_id,
                Role.organization_id == organization_id,
            )
        )
        if role is None:
            raise IdentityNotFoundError
        return role

    def create_role(
        self,
        *,
        actor: User,
        name: str,
        slug: str,
        description: str,
        permission_codes: list[str],
        correlation_id: str,
    ) -> Role:
        normalized_slug = slug.strip().lower()
        if (
            self.session.scalar(
                select(Role.id).where(
                    Role.organization_id == actor.organization_id,
                    Role.slug == normalized_slug,
                )
            )
            is not None
        ):
            raise IdentityConflictError
        role = Role(
            organization_id=actor.organization_id,
            name=name.strip(),
            slug=normalized_slug,
            description=description.strip(),
            is_system=False,
        )
        self.session.add(role)
        self.session.flush()
        self._set_role_permissions(actor, role, permission_codes)
        self._audit(
            actor,
            "identity.role_created",
            "role",
            role.id,
            correlation_id,
            {"slug": role.slug, "permissions": permission_codes},
        )
        self.session.commit()
        self.session.refresh(role)
        return role

    def update_role(
        self,
        *,
        actor: User,
        role_id: str,
        name: str,
        description: str,
        permission_codes: list[str],
        correlation_id: str,
    ) -> Role:
        role = self.get_role(actor.organization_id, role_id)
        if role.slug == "admin" and "system.admin" not in permission_codes:
            raise IdentityValidationError
        role.name = name.strip()
        role.description = description.strip()
        self._set_role_permissions(actor, role, permission_codes)
        self._audit(
            actor,
            "identity.role_updated",
            "role",
            role.id,
            correlation_id,
            {"permissions": permission_codes},
        )
        self.session.commit()
        self.session.refresh(role)
        return role

    def delete_role(
        self,
        *,
        actor: User,
        role_id: str,
        correlation_id: str,
    ) -> None:
        role = self.get_role(actor.organization_id, role_id)
        if role.is_system:
            raise IdentityValidationError
        if (
            self.session.scalar(
                select(UserRole.id).where(UserRole.role_id == role.id).limit(1)
            )
            is not None
        ):
            raise IdentityConflictError
        self._audit(
            actor,
            "identity.role_deleted",
            "role",
            role.id,
            correlation_id,
            {"slug": role.slug},
        )
        self.session.delete(role)
        self.session.commit()

    def list_users(self, organization_id: str) -> list[User]:
        return list(
            self.session.scalars(
                select(User)
                .where(User.organization_id == organization_id)
                .order_by(User.full_name, User.email)
            )
        )

    def get_user(self, organization_id: str, user_id: str) -> User:
        user = self.session.scalar(
            select(User).where(
                User.id == user_id,
                User.organization_id == organization_id,
            )
        )
        if user is None:
            raise IdentityNotFoundError
        return user

    def user_role_ids(self, user_id: str) -> list[str]:
        return list(
            self.session.scalars(
                select(UserRole.role_id)
                .where(UserRole.user_id == user_id)
                .order_by(UserRole.created_at)
            )
        )

    def user_mfa_enabled(self, user_id: str) -> bool:
        return bool(
            self.session.scalar(
                select(UserMfaMethod.enabled).where(UserMfaMethod.user_id == user_id)
            )
        )

    def create_user(
        self,
        *,
        actor: User,
        email: str,
        full_name: str,
        password: str,
        role_ids: list[str],
        correlation_id: str,
    ) -> User:
        normalized_email = email.strip().lower()
        if (
            self.session.scalar(
                select(User.id).where(
                    User.organization_id == actor.organization_id,
                    User.email == normalized_email,
                )
            )
            is not None
        ):
            raise IdentityConflictError
        roles = self._roles_for_assignment(actor.organization_id, role_ids)
        user = User(
            organization_id=actor.organization_id,
            email=normalized_email,
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            role=self._primary_role_slug(roles),
            is_active=True,
        )
        self.session.add(user)
        self.session.flush()
        self._assign_roles(actor, user, roles)
        self._audit(
            actor,
            "identity.user_created",
            "user",
            user.id,
            correlation_id,
            {"email": user.email, "role_ids": role_ids},
        )
        self.session.commit()
        self.session.refresh(user)
        return user

    def update_user(
        self,
        *,
        actor: User,
        user_id: str,
        email: str,
        full_name: str,
        role_ids: list[str],
        is_active: bool,
        password: str | None,
        correlation_id: str,
    ) -> User:
        user = self.get_user(actor.organization_id, user_id)
        normalized_email = email.strip().lower()
        duplicate = self.session.scalar(
            select(User.id).where(
                User.organization_id == actor.organization_id,
                User.email == normalized_email,
                User.id != user.id,
            )
        )
        if duplicate is not None:
            raise IdentityConflictError
        roles = self._roles_for_assignment(actor.organization_id, role_ids)
        if user.id == actor.id and not is_active:
            raise IdentityValidationError
        if user.id == actor.id and not any(role.slug == "admin" for role in roles):
            raise IdentityValidationError
        user.email = normalized_email
        user.full_name = full_name.strip()
        user.is_active = is_active
        user.role = self._primary_role_slug(roles)
        if password:
            user.password_hash = hash_password(password)
        self.session.execute(delete(UserRole).where(UserRole.user_id == user.id))
        self.session.flush()
        self._assign_roles(actor, user, roles)
        self._audit(
            actor,
            "identity.user_updated",
            "user",
            user.id,
            correlation_id,
            {
                "email": user.email,
                "role_ids": role_ids,
                "is_active": is_active,
                "password_changed": bool(password),
            },
        )
        self.session.commit()
        self.session.refresh(user)
        return user

    def list_tokens(self, user: User) -> list[ApiToken]:
        return list(
            self.session.scalars(
                select(ApiToken)
                .where(
                    ApiToken.organization_id == user.organization_id,
                    ApiToken.user_id == user.id,
                )
                .order_by(ApiToken.created_at.desc())
            )
        )

    def create_token(
        self,
        *,
        actor: User,
        name: str,
        scopes: list[str],
        expires_at: datetime | None,
        correlation_id: str,
    ) -> tuple[ApiToken, str]:
        requested = set(scopes)
        allowed = effective_permissions(self.session, actor)
        if not requested or not requested.issubset(allowed):
            raise IdentityValidationError
        if expires_at is not None and expires_at <= datetime.now(UTC):
            raise IdentityValidationError
        raw_token = f"airk_{token_urlsafe(36)}"
        token = ApiToken(
            organization_id=actor.organization_id,
            user_id=actor.id,
            name=name.strip(),
            token_prefix=raw_token[:16],
            token_hash=api_token_hash(raw_token, self.settings),
            scopes=sorted(requested),
            expires_at=expires_at,
        )
        self.session.add(token)
        self.session.flush()
        self._audit(
            actor,
            "identity.api_token_created",
            "api_token",
            token.id,
            correlation_id,
            {"name": token.name, "scopes": token.scopes},
        )
        self.session.commit()
        self.session.refresh(token)
        return token, raw_token

    def revoke_token(
        self,
        *,
        actor: User,
        token_id: str,
        correlation_id: str,
    ) -> ApiToken:
        token = self.session.scalar(
            select(ApiToken).where(
                ApiToken.id == token_id,
                ApiToken.organization_id == actor.organization_id,
                ApiToken.user_id == actor.id,
            )
        )
        if token is None:
            raise IdentityNotFoundError
        if token.revoked_at is None:
            token.revoked_at = utc_now()
            self._audit(
                actor,
                "identity.api_token_revoked",
                "api_token",
                token.id,
                correlation_id,
                {"name": token.name},
            )
            self.session.commit()
            self.session.refresh(token)
        return token

    def _set_role_permissions(
        self,
        actor: User,
        role: Role,
        permission_codes: list[str],
    ) -> None:
        requested = set(permission_codes)
        if not requested or not requested.issubset(ALL_PERMISSION_CODES):
            raise IdentityValidationError
        permissions = list(
            self.session.scalars(
                select(Permission).where(Permission.code.in_(requested))
            )
        )
        if len(permissions) != len(requested):
            raise IdentityValidationError
        self.session.execute(
            delete(RolePermission).where(RolePermission.role_id == role.id)
        )
        self.session.flush()
        for permission in permissions:
            self.session.add(
                RolePermission(
                    organization_id=actor.organization_id,
                    role_id=role.id,
                    permission_id=permission.id,
                    granted_by=actor.id,
                )
            )

    def _roles_for_assignment(
        self,
        organization_id: str,
        role_ids: list[str],
    ) -> list[Role]:
        if not role_ids:
            raise IdentityValidationError
        roles = list(
            self.session.scalars(
                select(Role).where(
                    Role.organization_id == organization_id,
                    Role.id.in_(set(role_ids)),
                )
            )
        )
        if len(roles) != len(set(role_ids)):
            raise IdentityValidationError
        return roles

    def _assign_roles(self, actor: User, user: User, roles: list[Role]) -> None:
        for role in roles:
            self.session.add(
                UserRole(
                    organization_id=actor.organization_id,
                    user_id=user.id,
                    role_id=role.id,
                    assigned_by=actor.id,
                )
            )

    @staticmethod
    def _primary_role_slug(roles: list[Role]) -> str:
        priority = ("admin", "manager", "warehouse", "viewer", "service")
        slugs = {role.slug for role in roles}
        for slug in priority:
            if slug in slugs:
                return "plugin" if slug == "service" else slug
        return sorted(slugs)[0]

    def _audit(
        self,
        actor: User,
        action: str,
        entity_type: str,
        entity_id: str,
        correlation_id: str,
        details: dict,
    ) -> None:
        self.session.add(
            AuditLog(
                organization_id=actor.organization_id,
                actor_id=actor.id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                correlation_id=correlation_id,
                details=details,
            )
        )
