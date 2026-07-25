from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DbSession, require_permissions
from app.models import Role, UserRole
from app.schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenRead,
    PermissionRead,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    UserAdminCreate,
    UserAdminRead,
    UserAdminUpdate,
)
from app.services.identity import (
    IdentityConflictError,
    IdentityError,
    IdentityNotFoundError,
    IdentityService,
    IdentityValidationError,
    effective_permissions,
    effective_role_slugs,
)

router = APIRouter(prefix="/identity", tags=["identity"])

UserViewer = Annotated[object, Depends(require_permissions("users.read"))]
UserAdmin = Annotated[object, Depends(require_permissions("users.write"))]
RoleViewer = Annotated[object, Depends(require_permissions("roles.read"))]
RoleAdmin = Annotated[object, Depends(require_permissions("roles.write"))]
TokenViewer = Annotated[object, Depends(require_permissions("tokens.read"))]
TokenCreator = Annotated[object, Depends(require_permissions("tokens.create"))]
TokenRevoker = Annotated[object, Depends(require_permissions("tokens.revoke"))]


def _error(exc: IdentityError) -> HTTPException:
    if isinstance(exc, IdentityNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": exc.code,
                "message": "A felhasználó, szerepkör vagy token nem található.",
            },
        )
    if isinstance(exc, IdentityConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": "Az e-mail, szerepkör vagy hozzárendelés már létezik.",
            },
        )
    if isinstance(exc, IdentityValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.code,
                "message": "A jogosultsági beállítás nem érvényes.",
            },
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": exc.code, "message": "Az identity művelet sikertelen."},
    )


def _identity(session: DbSession, organization_id: str) -> IdentityService:
    service = IdentityService(session)
    service.ensure_organization(organization_id)
    session.commit()
    return service


def _role_read(
    session: DbSession,
    service: IdentityService,
    role: Role,
) -> RoleRead:
    user_count = session.scalar(
        select(func.count(UserRole.id)).where(UserRole.role_id == role.id)
    )
    return RoleRead(
        id=role.id,
        organization_id=role.organization_id,
        name=role.name,
        slug=role.slug,
        description=role.description,
        is_system=role.is_system,
        permission_codes=service.role_permission_codes(role.id),
        user_count=int(user_count or 0),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


def _user_read(
    session: DbSession,
    service: IdentityService,
    user,
) -> UserAdminRead:
    return UserAdminRead(
        id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        role_ids=service.user_role_ids(user.id),
        roles=sorted(effective_role_slugs(session, user)),
        permissions=sorted(effective_permissions(session, user)),
        mfa_enabled=service.user_mfa_enabled(user.id),
        mfa_required="admin" in effective_role_slugs(session, user),
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get("/permissions", response_model=list[PermissionRead])
def list_permissions(
    session: DbSession,
    user: CurrentUser,
    _: RoleViewer,
) -> list:
    return _identity(session, user.organization_id).list_permissions()


@router.get("/roles", response_model=list[RoleRead])
def list_roles(
    session: DbSession,
    user: CurrentUser,
    _: RoleViewer,
) -> list[RoleRead]:
    service = _identity(session, user.organization_id)
    return [
        _role_read(session, service, role)
        for role in service.list_roles(user.organization_id)
    ]


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    _: RoleAdmin,
) -> RoleRead:
    service = _identity(session, user.organization_id)
    try:
        role = service.create_role(
            actor=user,
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            permission_codes=payload.permission_codes,
            correlation_id=request.state.correlation_id,
        )
        return _role_read(session, service, role)
    except IdentityError as exc:
        session.rollback()
        raise _error(exc) from exc


@router.patch("/roles/{role_id}", response_model=RoleRead)
def update_role(
    role_id: str,
    payload: RoleUpdate,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    _: RoleAdmin,
) -> RoleRead:
    service = _identity(session, user.organization_id)
    try:
        role = service.update_role(
            actor=user,
            role_id=role_id,
            name=payload.name,
            description=payload.description,
            permission_codes=payload.permission_codes,
            correlation_id=request.state.correlation_id,
        )
        return _role_read(session, service, role)
    except IdentityError as exc:
        session.rollback()
        raise _error(exc) from exc


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: str,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    _: RoleAdmin,
) -> None:
    service = _identity(session, user.organization_id)
    try:
        service.delete_role(
            actor=user,
            role_id=role_id,
            correlation_id=request.state.correlation_id,
        )
    except IdentityError as exc:
        session.rollback()
        raise _error(exc) from exc


@router.get("/users", response_model=list[UserAdminRead])
def list_users(
    session: DbSession,
    user: CurrentUser,
    _: UserViewer,
) -> list[UserAdminRead]:
    service = _identity(session, user.organization_id)
    return [
        _user_read(session, service, listed_user)
        for listed_user in service.list_users(user.organization_id)
    ]


@router.post("/users", response_model=UserAdminRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserAdminCreate,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    _: UserAdmin,
) -> UserAdminRead:
    service = _identity(session, user.organization_id)
    try:
        created = service.create_user(
            actor=user,
            email=str(payload.email),
            full_name=payload.full_name,
            password=payload.password,
            role_ids=payload.role_ids,
            correlation_id=request.state.correlation_id,
        )
        return _user_read(session, service, created)
    except IdentityError as exc:
        session.rollback()
        raise _error(exc) from exc


@router.patch("/users/{user_id}", response_model=UserAdminRead)
def update_user(
    user_id: str,
    payload: UserAdminUpdate,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    _: UserAdmin,
) -> UserAdminRead:
    service = _identity(session, user.organization_id)
    try:
        updated = service.update_user(
            actor=user,
            user_id=user_id,
            email=str(payload.email),
            full_name=payload.full_name,
            role_ids=payload.role_ids,
            is_active=payload.is_active,
            password=payload.password,
            correlation_id=request.state.correlation_id,
        )
        return _user_read(session, service, updated)
    except IdentityError as exc:
        session.rollback()
        raise _error(exc) from exc


@router.get("/tokens", response_model=list[ApiTokenRead])
def list_api_tokens(
    session: DbSession,
    user: CurrentUser,
    _: TokenViewer,
) -> list:
    return _identity(session, user.organization_id).list_tokens(user)


@router.post(
    "/tokens",
    response_model=ApiTokenCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_api_token(
    payload: ApiTokenCreate,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    _: TokenCreator,
) -> ApiTokenCreated:
    service = _identity(session, user.organization_id)
    try:
        token, raw_token = service.create_token(
            actor=user,
            name=payload.name,
            scopes=payload.scopes,
            expires_at=payload.expires_at,
            correlation_id=request.state.correlation_id,
        )
        return ApiTokenCreated(
            token=ApiTokenRead.model_validate(token),
            raw_token=raw_token,
        )
    except IdentityError as exc:
        session.rollback()
        raise _error(exc) from exc


@router.delete("/tokens/{token_id}", response_model=ApiTokenRead)
def revoke_api_token(
    token_id: str,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    _: TokenRevoker,
) -> ApiTokenRead:
    service = _identity(session, user.organization_id)
    try:
        return ApiTokenRead.model_validate(
            service.revoke_token(
                actor=user,
                token_id=token_id,
                correlation_id=request.state.correlation_id,
            )
        )
    except IdentityError as exc:
        session.rollback()
        raise _error(exc) from exc
