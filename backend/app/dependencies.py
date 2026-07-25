from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import ApiToken, RefreshSession, User, UserMfaMethod, utc_now
from app.security import api_token_hash, decode_access_token
from app.services.identity import (
    effective_permissions,
    effective_role_slugs,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_current_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
    session: DbSession,
    settings: AppSettings,
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_credentials", "message": "Érvénytelen vagy lejárt munkamenet."},
        headers={"WWW-Authenticate": "Bearer"},
    )
    now = datetime.now(UTC)
    if token.startswith("airk_"):
        api_token = session.scalar(
            select(ApiToken).where(
                ApiToken.token_hash == api_token_hash(token, settings),
                ApiToken.revoked_at.is_(None),
                (ApiToken.expires_at.is_(None) | (ApiToken.expires_at > now)),
            )
        )
        if api_token is None:
            raise credentials_error
        user = session.scalar(
            select(User).where(
                User.id == api_token.user_id,
                User.organization_id == api_token.organization_id,
                User.is_active.is_(True),
            )
        )
        if user is None:
            raise credentials_error
        api_token.last_used_at = utc_now()
        session.commit()
        request.state.auth_type = "api_token"
        request.state.api_token_id = api_token.id
        request.state.api_scopes = frozenset(api_token.scopes)
        request.state.mfa_verified = True
        request.state.current_session_id = None
        return user

    try:
        payload = decode_access_token(token, settings)
    except jwt.PyJWTError as exc:
        raise credentials_error from exc

    if payload.get("type") != "access":
        raise credentials_error

    user = session.scalar(
        select(User).where(
            User.id == payload["sub"],
            User.organization_id == payload["org"],
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise credentials_error
    session_id = payload.get("sid")
    if not isinstance(session_id, str) or not session_id:
        raise credentials_error
    refresh_session = session.scalar(
        select(RefreshSession).where(
            RefreshSession.id == session_id,
            RefreshSession.user_id == user.id,
            RefreshSession.organization_id == user.organization_id,
        )
    )
    comparison_now = (
        now
        if refresh_session is None or refresh_session.expires_at.tzinfo is not None
        else now.replace(tzinfo=None)
    )
    if (
        refresh_session is None
        or refresh_session.revoked_at is not None
        or refresh_session.expires_at <= comparison_now
    ):
        raise credentials_error
    request.state.auth_type = "access_token"
    request.state.api_token_id = None
    request.state.api_scopes = None
    request.state.mfa_verified = bool(payload.get("mfa", False))
    request.state.current_session_id = session_id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_interactive_user(request: Request, user: CurrentUser) -> User:
    if getattr(request.state, "auth_type", "") != "access_token":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "interactive_session_required",
                "message": "Ehhez a művelethez interaktív munkamenet szükséges.",
            },
        )
    return user


InteractiveUser = Annotated[User, Depends(get_interactive_user)]


def require_roles(*roles: str) -> Callable:
    def dependency(
        request: Request,
        user: CurrentUser,
        session: DbSession,
        settings: AppSettings,
    ) -> User:
        if not effective_role_slugs(session, user).intersection(roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "forbidden",
                    "message": "Ehhez a művelethez nincs megfelelő jogosultság.",
                },
            )
        _enforce_privileged_mfa(request, session, settings, user)
        return user

    return dependency


def require_permissions(*permissions: str) -> Callable:
    required = frozenset(permissions)

    def dependency(
        request: Request,
        user: CurrentUser,
        session: DbSession,
        settings: AppSettings,
    ) -> User:
        authorize_permissions(
            request,
            session,
            settings,
            user,
            *required,
        )
        return user

    return dependency


def authorize_permissions(
    request: Request,
    session: Session,
    settings: Settings,
    user: User,
    *permissions: str,
) -> None:
    required = frozenset(permissions)
    granted = effective_permissions(session, user)
    if not required.issubset(granted):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "forbidden",
                "message": "Ehhez a művelethez nincs megfelelő jogosultság.",
                "required_permissions": sorted(required),
            },
        )
    token_scopes = getattr(request.state, "api_scopes", None)
    if token_scopes is not None and not required.issubset(token_scopes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "api_token_scope_denied",
                "message": "Az API-token hatóköre nem engedi ezt a műveletet.",
                "required_permissions": sorted(required),
            },
        )
    _enforce_privileged_mfa(request, session, settings, user)


def _enforce_privileged_mfa(
    request: Request,
    session: Session,
    settings: Settings,
    user: User,
) -> None:
    if not settings.mfa_enforce_admin:
        return
    if getattr(request.state, "auth_type", "") == "api_token":
        return
    if "admin" not in effective_role_slugs(session, user):
        return
    method = session.scalar(
        select(UserMfaMethod).where(UserMfaMethod.user_id == user.id)
    )
    if method is None or not method.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "mfa_setup_required",
                "message": "Adminisztrátori művelet előtt be kell állítani az MFA-t.",
            },
        )
    if not getattr(request.state, "mfa_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "mfa_required",
                "message": "Ehhez a művelethez MFA-val hitelesített munkamenet szükséges.",
            },
        )
