import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import jwt
from pwdlib import PasswordHash

from src.config import settings
from src.errors import ErrorCode

ACCESS_TOKEN_TYPE = "access"  # noqa: S105
REFRESH_TOKEN_TYPE = "refresh"  # noqa: S105

password_hash = PasswordHash.recommended()


class TokenDecodeError(Exception):
    def __init__(self, code: ErrorCode):
        self.code = code
        super().__init__(str(code))


def _read_jwt_key(path: Path, key_name: str) -> str:
    try:
        return path.read_text()
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"JWT {key_name} key file not found at '{path}'. "
            "Set LIGHTTASK_CONFIG__AUTH_JWT__*_KEY_PATH to existing files."
        ) from exc


@lru_cache(maxsize=1)
def _jwt_material() -> tuple[str, str, str]:
    private_key = _read_jwt_key(settings.auth_jwt.private_key_path, "private")
    public_key = _read_jwt_key(settings.auth_jwt.public_key_path, "public")
    algorithm = settings.auth_jwt.algorithm
    return private_key, public_key, algorithm


def encode_jwt(
    payload: dict[str, Any],
    expire_minutes: int,
) -> str:
    private_key, _, algorithm = _jwt_material()

    to_encode = payload.copy()
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=expire_minutes)

    to_encode.update(
        exp=expire,
        iat=now,
        jti=str(uuid.uuid4()),
    )

    return jwt.encode(
        to_encode,
        private_key,
        algorithm=algorithm,
    )


def decode_jwt(token: str) -> dict[str, Any]:
    _, public_key, algorithm = _jwt_material()

    try:
        return jwt.decode(token, public_key, algorithms=[algorithm])
    except jwt.ExpiredSignatureError as err:
        raise TokenDecodeError(ErrorCode.TOKEN_EXPIRED) from err
    except jwt.PyJWTError as err:
        raise TokenDecodeError(ErrorCode.COULD_NOT_VALIDATE) from err


def create_access_token(
    user_data: dict[str, Any],
    expire_minutes: int = settings.auth_jwt.access_token_expire_minutes,
) -> str:
    payload = user_data.copy()
    payload.update({"type": ACCESS_TOKEN_TYPE})
    return encode_jwt(
        payload,
        expire_minutes=expire_minutes,
    )


def create_refresh_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "type": REFRESH_TOKEN_TYPE,
    }
    expire_minutes = settings.auth_jwt.refresh_token_expire_days * 24 * 60
    return encode_jwt(
        payload,
        expire_minutes=expire_minutes,
    )


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def validate_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)
