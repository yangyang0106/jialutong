import hashlib
from datetime import UTC, datetime


SESSION_DAYS = 30
BIND_CODE_MINUTES = 30

FAMILY_ADMIN = "FAMILY_ADMIN"
FAMILY_MEMBER = "FAMILY_MEMBER"
ELDER_USER = "ELDER_USER"
SUPER_ADMIN = "SUPER_ADMIN"


def now() -> datetime:
    return datetime.now(UTC)


def now_iso() -> str:
    return now().isoformat()


def parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    ).hex()


def normalize_code(value: str) -> str:
    return "".join(ch for ch in value.upper().strip() if ch.isalnum())
