import base64
import hmac
import struct
from datetime import UTC, datetime, timedelta
from hashlib import sha1, sha256
from secrets import choice, token_bytes, token_urlsafe
from urllib.parse import quote

import jwt
from cryptography.fernet import Fernet
from pwdlib import PasswordHash

from app.config import Settings
from app.models import User

password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hash.verify(password, encoded_hash)


def create_access_token(
    user: User,
    settings: Settings,
    *,
    mfa_verified: bool = False,
    session_id: str | None = None,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "org": user.organization_id,
        "role": user.role,
        "mfa": mfa_verified,
        "sid": session_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> dict:
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[ALGORITHM],
        options={"require": ["sub", "org", "exp", "type"]},
    )


def create_mfa_challenge_token(user: User, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user.id,
            "org": user.organization_id,
            "iat": now,
            "exp": now + timedelta(minutes=settings.mfa_challenge_minutes),
            "type": "mfa_challenge",
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def decode_mfa_challenge_token(token: str, settings: Settings) -> dict:
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[ALGORITHM],
        options={"require": ["sub", "org", "exp", "type"]},
    )


def new_refresh_token() -> str:
    return token_urlsafe(48)


def refresh_token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def api_token_hash(token: str, settings: Settings) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        token.encode("utf-8"),
        sha256,
    ).hexdigest()


def recovery_code_hash(code: str, settings: Settings) -> str:
    normalized = code.replace("-", "").strip().upper()
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        normalized.encode("ascii"),
        sha256,
    ).hexdigest()


def generate_mfa_secret() -> str:
    return base64.b32encode(token_bytes(20)).decode("ascii").rstrip("=")


def encrypt_secret(secret: str, settings: Settings) -> str:
    key = base64.urlsafe_b64encode(sha256(settings.secret_key.encode("utf-8")).digest())
    return Fernet(key).encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_secret(encrypted: str, settings: Settings) -> str:
    key = base64.urlsafe_b64encode(sha256(settings.secret_key.encode("utf-8")).digest())
    return Fernet(key).decrypt(encrypted.encode("ascii")).decode("utf-8")


def encrypt_mfa_secret(secret: str, settings: Settings) -> str:
    return encrypt_secret(secret, settings)


def decrypt_mfa_secret(encrypted: str, settings: Settings) -> str:
    return decrypt_secret(encrypted, settings)


def create_totp_uri(
    *,
    secret: str,
    issuer: str,
    organization_slug: str,
    email: str,
) -> str:
    label = quote(f"{issuer}:{organization_slug}:{email}")
    return (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )


def totp_code(secret: str, counter: int) -> str:
    padding = "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(secret + padding, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), sha1).digest()
    offset = digest[-1] & 0x0F
    binary = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return f"{binary % 1_000_000:06d}"


def verify_totp(
    secret: str,
    code: str,
    *,
    now: datetime | None = None,
    last_used_counter: int | None = None,
) -> int | None:
    normalized = code.replace(" ", "").strip()
    if len(normalized) != 6 or not normalized.isdigit():
        return None
    reference = now or datetime.now(UTC)
    counter = int(reference.timestamp()) // 30
    for candidate in (counter - 1, counter, counter + 1):
        if last_used_counter is not None and candidate <= last_used_counter:
            continue
        if hmac.compare_digest(totp_code(secret, candidate), normalized):
            return candidate
    return None


RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_recovery_codes(count: int = 8) -> list[str]:
    return [
        f"{''.join(choice(RECOVERY_ALPHABET) for _ in range(5))}-"
        f"{''.join(choice(RECOVERY_ALPHABET) for _ in range(5))}"
        for _ in range(count)
    ]
