from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import delete, select, update

from app.config import Settings, get_settings
from app.dependencies import DbSession, InteractiveUser
from app.models import (
    AuditLog,
    MfaRecoveryCode,
    Organization,
    RefreshSession,
    User,
    UserMfaMethod,
    utc_now,
)
from app.schemas import (
    LoginRequest,
    MfaChallengeResponse,
    MfaConfirmRequest,
    MfaConfirmResponse,
    MfaDisableRequest,
    MfaSetupRead,
    MfaVerifyRequest,
    RefreshRequest,
    RefreshSessionRead,
    TokenResponse,
    UserSummary,
)
from app.security import (
    create_access_token,
    create_mfa_challenge_token,
    create_totp_uri,
    decode_mfa_challenge_token,
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_mfa_secret,
    generate_recovery_codes,
    new_refresh_token,
    recovery_code_hash,
    refresh_token_hash,
    verify_password,
    verify_totp,
)
from app.services.identity import (
    IdentityService,
    effective_permissions,
    effective_role_slugs,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _request_context(request: Request) -> tuple[str, str]:
    ip_address = request.client.host if request.client else ""
    user_agent = request.headers.get("User-Agent", "")[:500]
    return ip_address[:64], user_agent


def _user_summary(
    session: DbSession,
    user: User,
    settings: Settings,
) -> UserSummary:
    identity = IdentityService(session, settings=settings)
    identity.ensure_organization(user.organization_id)
    session.flush()
    roles = sorted(effective_role_slugs(session, user))
    role_ids = identity.user_role_ids(user.id)
    mfa_enabled = identity.user_mfa_enabled(user.id)
    return UserSummary(
        id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        role_ids=role_ids,
        roles=roles,
        permissions=sorted(effective_permissions(session, user)),
        mfa_enabled=mfa_enabled,
        mfa_required=settings.mfa_enforce_admin and "admin" in roles,
    )


def _issue_tokens(
    session: DbSession,
    user: User,
    request: Request,
    *,
    mfa_verified: bool,
    family_id: str | None = None,
    replaces: RefreshSession | None = None,
) -> TokenResponse:
    settings = get_settings()
    refresh_token = new_refresh_token()
    ip_address, user_agent = _request_context(request)
    refresh_session = RefreshSession(
        user_id=user.id,
        organization_id=user.organization_id,
        token_hash=refresh_token_hash(refresh_token),
        family_id=family_id or str(uuid4()),
        mfa_verified=mfa_verified,
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
    )
    session.add(refresh_session)
    session.flush()
    if replaces is not None:
        replaces.replaced_by_session_id = refresh_session.id
    summary = _user_summary(session, user, settings)
    session.commit()
    return TokenResponse(
        access_token=create_access_token(
            user,
            settings,
            mfa_verified=mfa_verified,
            session_id=refresh_session.id,
        ),
        refresh_token=refresh_token,
        expires_in=settings.access_token_minutes * 60,
        user=summary,
        mfa_setup_required=(
            settings.mfa_enforce_admin
            and "admin" in summary.roles
            and not summary.mfa_enabled
        ),
    )


def _verify_mfa_code(
    session: DbSession,
    method: UserMfaMethod,
    code: str,
    settings: Settings,
) -> bool:
    secret = decrypt_mfa_secret(method.secret_encrypted, settings)
    counter = verify_totp(
        secret,
        code,
        last_used_counter=method.last_used_counter,
    )
    if counter is not None:
        method.last_used_counter = counter
        return True
    code_hash = recovery_code_hash(code, settings)
    recovery = session.scalar(
        select(MfaRecoveryCode).where(
            MfaRecoveryCode.mfa_method_id == method.id,
            MfaRecoveryCode.code_hash == code_hash,
            MfaRecoveryCode.used_at.is_(None),
        )
    )
    if recovery is None:
        return False
    recovery.used_at = utc_now()
    return True


@router.post("/login", response_model=TokenResponse | MfaChallengeResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: DbSession,
) -> TokenResponse | MfaChallengeResponse:
    organization = session.scalar(
        select(Organization).where(
            Organization.slug == payload.organization_slug.lower()
        )
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
            detail={
                "code": "invalid_credentials",
                "message": "Hibás bejelentkezési adatok.",
            },
        )

    settings = get_settings()
    method = session.scalar(
        select(UserMfaMethod).where(
            UserMfaMethod.user_id == user.id,
            UserMfaMethod.enabled.is_(True),
        )
    )
    if method is not None:
        return MfaChallengeResponse(
            challenge_token=create_mfa_challenge_token(user, settings),
            expires_in=settings.mfa_challenge_minutes * 60,
        )
    return _issue_tokens(session, user, request, mfa_verified=False)


@router.post("/mfa/verify", response_model=TokenResponse)
def verify_mfa_challenge(
    payload: MfaVerifyRequest,
    request: Request,
    session: DbSession,
) -> TokenResponse:
    settings = get_settings()
    try:
        claims = decode_mfa_challenge_token(payload.challenge_token, settings)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_mfa_challenge",
                "message": "Az MFA-kérés lejárt vagy érvénytelen.",
            },
        ) from exc
    if claims.get("type") != "mfa_challenge":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_mfa_challenge",
                "message": "Az MFA-kérés érvénytelen.",
            },
        )
    user = session.scalar(
        select(User).where(
            User.id == claims["sub"],
            User.organization_id == claims["org"],
            User.is_active.is_(True),
        )
    )
    method = (
        session.scalar(
            select(UserMfaMethod)
            .where(
                UserMfaMethod.user_id == user.id,
                UserMfaMethod.enabled.is_(True),
            )
            .with_for_update()
        )
        if user is not None
        else None
    )
    if method is None or not _verify_mfa_code(
        session,
        method,
        payload.code,
        settings,
    ):
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_mfa_code", "message": "Hibás MFA-kód."},
        )
    return _issue_tokens(session, user, request, mfa_verified=True)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    request: Request,
    session: DbSession,
) -> TokenResponse:
    now = datetime.now(UTC)
    token_hash = refresh_token_hash(payload.refresh_token)
    refresh_session = session.scalar(
        select(RefreshSession)
        .where(RefreshSession.token_hash == token_hash)
        .with_for_update()
    )
    comparison_now = (
        now
        if refresh_session is None or refresh_session.expires_at.tzinfo is not None
        else now.replace(tzinfo=None)
    )
    if refresh_session is None or refresh_session.expires_at <= comparison_now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_refresh_token", "message": "A munkamenet lejárt."},
        )
    if refresh_session.revoked_at is not None:
        session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.family_id == refresh_session.family_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoke_reason="REFRESH_REUSE_DETECTED")
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "refresh_token_reuse",
                "message": "A munkamenet biztonsági okból visszavonásra került.",
            },
        )
    user = session.scalar(
        select(User).where(
            User.id == refresh_session.user_id,
            User.organization_id == refresh_session.organization_id,
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "inactive_user", "message": "A felhasználó nem aktív."},
        )
    refresh_session.revoked_at = now
    refresh_session.revoke_reason = "ROTATED"
    refresh_session.last_seen_at = now
    session.flush()
    return _issue_tokens(
        session,
        user,
        request,
        mfa_verified=refresh_session.mfa_verified,
        family_id=refresh_session.family_id,
        replaces=refresh_session,
    )


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
        refresh_session.revoke_reason = "LOGOUT"
        session.commit()


@router.post("/mfa/setup", response_model=MfaSetupRead)
def setup_mfa(
    request: Request,
    session: DbSession,
    user: InteractiveUser,
) -> MfaSetupRead:
    settings = get_settings()
    secret = generate_mfa_secret()
    method = session.scalar(
        select(UserMfaMethod).where(UserMfaMethod.user_id == user.id)
    )
    if method is None:
        method = UserMfaMethod(
            user_id=user.id,
            secret_encrypted=encrypt_mfa_secret(secret, settings),
            enabled=False,
        )
        session.add(method)
    elif not method.enabled:
        method.secret_encrypted = encrypt_mfa_secret(secret, settings)
        method.last_used_counter = None
        session.execute(
            delete(MfaRecoveryCode).where(
                MfaRecoveryCode.mfa_method_id == method.id
            )
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "mfa_already_enabled",
                "message": "Az MFA már be van kapcsolva.",
            },
        )
    organization = session.get(Organization, user.organization_id)
    session.add(
        AuditLog(
            organization_id=user.organization_id,
            actor_id=user.id,
            action="identity.mfa_setup_started",
            entity_type="user",
            entity_id=user.id,
            correlation_id=request.state.correlation_id,
            details={},
        )
    )
    session.commit()
    return MfaSetupRead(
        secret=secret,
        otpauth_uri=create_totp_uri(
            secret=secret,
            issuer=settings.mfa_issuer,
            organization_slug=organization.slug if organization else "organization",
            email=user.email,
        ),
    )


@router.post("/mfa/confirm", response_model=MfaConfirmResponse)
def confirm_mfa(
    payload: MfaConfirmRequest,
    request: Request,
    session: DbSession,
    user: InteractiveUser,
) -> MfaConfirmResponse:
    settings = get_settings()
    method = session.scalar(
        select(UserMfaMethod)
        .where(UserMfaMethod.user_id == user.id)
        .with_for_update()
    )
    if method is None or method.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "mfa_setup_not_pending",
                "message": "Nincs megerősítésre váró MFA-beállítás.",
            },
        )
    secret = decrypt_mfa_secret(method.secret_encrypted, settings)
    counter = verify_totp(secret, payload.code)
    if counter is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_mfa_code", "message": "Hibás MFA-kód."},
        )
    method.enabled = True
    method.confirmed_at = utc_now()
    method.last_used_counter = counter
    recovery_codes = generate_recovery_codes()
    for code in recovery_codes:
        session.add(
            MfaRecoveryCode(
                mfa_method_id=method.id,
                code_hash=recovery_code_hash(code, settings),
            )
        )
    current_session_id = getattr(request.state, "current_session_id", None)
    current_session = (
        session.get(RefreshSession, current_session_id)
        if current_session_id
        else None
    )
    if current_session is not None and current_session.revoked_at is None:
        current_session.revoked_at = utc_now()
        current_session.revoke_reason = "MFA_ENABLED"
    session.add(
        AuditLog(
            organization_id=user.organization_id,
            actor_id=user.id,
            action="identity.mfa_enabled",
            entity_type="user",
            entity_id=user.id,
            correlation_id=request.state.correlation_id,
            details={"recovery_code_count": len(recovery_codes)},
        )
    )
    session.flush()
    replacement = _issue_tokens(session, user, request, mfa_verified=True)
    return MfaConfirmResponse(
        recovery_codes=recovery_codes,
        session=replacement,
    )


@router.delete("/mfa", status_code=status.HTTP_204_NO_CONTENT)
def disable_mfa(
    payload: MfaDisableRequest,
    request: Request,
    session: DbSession,
    user: InteractiveUser,
) -> None:
    settings = get_settings()
    if settings.mfa_enforce_admin and "admin" in effective_role_slugs(session, user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "mfa_required_for_admin",
                "message": "Adminisztrátori fióknál az MFA nem kapcsolható ki.",
            },
        )
    method = session.scalar(
        select(UserMfaMethod)
        .where(
            UserMfaMethod.user_id == user.id,
            UserMfaMethod.enabled.is_(True),
        )
        .with_for_update()
    )
    if (
        method is None
        or not verify_password(payload.password, user.password_hash)
        or not _verify_mfa_code(session, method, payload.code, settings)
    ):
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_credentials",
                "message": "A jelszó vagy az MFA-kód hibás.",
            },
        )
    session.delete(method)
    session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.user_id == user.id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now(), revoke_reason="MFA_DISABLED")
    )
    session.add(
        AuditLog(
            organization_id=user.organization_id,
            actor_id=user.id,
            action="identity.mfa_disabled",
            entity_type="user",
            entity_id=user.id,
            correlation_id=request.state.correlation_id,
            details={},
        )
    )
    session.commit()


@router.get("/sessions", response_model=list[RefreshSessionRead])
def list_sessions(
    request: Request,
    session: DbSession,
    user: InteractiveUser,
) -> list[RefreshSessionRead]:
    current_id = getattr(request.state, "current_session_id", None)
    sessions = session.scalars(
        select(RefreshSession)
        .where(
            RefreshSession.user_id == user.id,
            RefreshSession.organization_id == user.organization_id,
        )
        .order_by(RefreshSession.created_at.desc())
        .limit(100)
    )
    return [
        RefreshSessionRead.model_validate(item).model_copy(
            update={"current": item.id == current_id}
        )
        for item in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: str,
    request: Request,
    session: DbSession,
    user: InteractiveUser,
) -> None:
    target = session.scalar(
        select(RefreshSession).where(
            RefreshSession.id == session_id,
            RefreshSession.user_id == user.id,
            RefreshSession.organization_id == user.organization_id,
        )
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "session_not_found",
                "message": "A munkamenet nem található.",
            },
        )
    if target.revoked_at is None:
        target.revoked_at = utc_now()
        target.revoke_reason = "USER_REVOKED"
        session.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_id=user.id,
                action="identity.session_revoked",
                entity_type="refresh_session",
                entity_id=target.id,
                correlation_id=request.state.correlation_id,
                details={
                    "current": target.id
                    == getattr(request.state, "current_session_id", None)
                },
            )
        )
        session.commit()


@router.post("/sessions/revoke-others", status_code=status.HTTP_204_NO_CONTENT)
def revoke_other_sessions(
    request: Request,
    session: DbSession,
    user: InteractiveUser,
) -> None:
    current_id = getattr(request.state, "current_session_id", None)
    statement = update(RefreshSession).where(
        RefreshSession.user_id == user.id,
        RefreshSession.organization_id == user.organization_id,
        RefreshSession.revoked_at.is_(None),
    )
    if current_id:
        statement = statement.where(RefreshSession.id != current_id)
    session.execute(
        statement.values(revoked_at=utc_now(), revoke_reason="USER_REVOKED_OTHERS")
    )
    session.add(
        AuditLog(
            organization_id=user.organization_id,
            actor_id=user.id,
            action="identity.other_sessions_revoked",
            entity_type="user",
            entity_id=user.id,
            correlation_id=request.state.correlation_id,
            details={},
        )
    )
    session.commit()
