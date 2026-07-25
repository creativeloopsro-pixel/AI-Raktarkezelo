from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import get_settings
from app.dependencies import DbSession
from app.models import Organization, RefreshSession, User
from app.schemas import LoginRequest, RefreshRequest, TokenResponse, UserSummary
from app.security import (
    create_access_token,
    new_refresh_token,
    refresh_token_hash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _issue_tokens(session: DbSession, user: User) -> TokenResponse:
    settings = get_settings()
    refresh_token = new_refresh_token()
    session.add(
        RefreshSession(
            user_id=user.id,
            token_hash=refresh_token_hash(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    session.commit()
    return TokenResponse(
        access_token=create_access_token(user, settings),
        refresh_token=refresh_token,
        expires_in=settings.access_token_minutes * 60,
        user=UserSummary.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: DbSession) -> TokenResponse:
    organization = session.scalar(
        select(Organization).where(Organization.slug == payload.organization_slug.lower())
    )
    user = None
    if organization is not None:
        user = session.scalar(
            select(User).where(
                User.organization_id == organization.id,
                User.email == payload.email.lower(),
                User.is_active.is_(True),
            )
        )

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Hibás bejelentkezési adatok."},
        )
    return _issue_tokens(session, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, session: DbSession) -> TokenResponse:
    now = datetime.now(UTC)
    refresh_session = session.scalar(
        select(RefreshSession)
        .where(
            RefreshSession.token_hash == refresh_token_hash(payload.refresh_token),
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > now,
        )
        .with_for_update()
    )
    if refresh_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_refresh_token", "message": "A munkamenet lejárt."},
        )
    user = session.scalar(
        select(User).where(User.id == refresh_session.user_id, User.is_active.is_(True))
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "inactive_user", "message": "A felhasználó nem aktív."},
        )
    refresh_session.revoked_at = now
    session.flush()
    return _issue_tokens(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, session: DbSession) -> None:
    refresh_session = session.scalar(
        select(RefreshSession).where(
            RefreshSession.token_hash == refresh_token_hash(payload.refresh_token),
            RefreshSession.revoked_at.is_(None),
        )
    )
    if refresh_session is not None:
        refresh_session.revoked_at = datetime.now(UTC)
        session.commit()
