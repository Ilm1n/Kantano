from __future__ import annotations

import re

SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "args",
        "kwargs",
    }
)

_URL_WITH_QUERY = re.compile(r"https?://[^\s\"'<>]+\?[^\s\"'<>]+")
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|cookie|password|secret|token|access_token|refresh_token|api_key)"
    r"\b\s*[:=]\s*(?:bearer\s+)?[^\s,;)\]}]+"
)


def is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    segments = set(normalized.split("_"))
    return (
        normalized in SENSITIVE_KEYS
        or bool(segments & {"authorization", "cookie", "password", "secret", "token"})
        or normalized.endswith("api_key")
    )


def redact_string(value: str) -> str:
    value = _URL_WITH_QUERY.sub(lambda match: match.group(0).split("?", 1)[0], value)
    value = _BEARER_TOKEN.sub("Bearer [REDACTED]", value)
    return _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        value,
    )
