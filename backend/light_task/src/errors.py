from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

_ERROR_CODE_RE = re.compile(r"^[A-Z0-9_]+$")


class ErrorCode(StrEnum):
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    COULD_NOT_VALIDATE = "COULD_NOT_VALIDATE"
    REFRESH_TOKEN_MISSING = "REFRESH_TOKEN_MISSING"
    INVALID_TOKEN_TYPE = "INVALID_TOKEN_TYPE"
    INVALID_TOKEN_PAYLOAD = "INVALID_TOKEN_PAYLOAD"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"

    USER_NOT_FOUND = "USER_NOT_FOUND"
    INACTIVE_USER = "INACTIVE_USER"
    USERNAME_OR_EMAIL_EXISTS = "USERNAME_OR_EMAIL_EXISTS"
    REGISTRATION_RATE_LIMITED = "REGISTRATION_RATE_LIMITED"
    REGISTRATION_RATE_LIMITER_UNAVAILABLE = "REGISTRATION_RATE_LIMITER_UNAVAILABLE"
    INVALID_OR_EXPIRED_VERIFICATION_TOKEN = "INVALID_OR_EXPIRED_VERIFICATION_TOKEN"
    EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
    USERNAME_TAKEN = "USERNAME_TAKEN"
    PASSWORD_LOGIN_UNAVAILABLE = "PASSWORD_LOGIN_UNAVAILABLE"
    CURRENT_PASSWORD_REQUIRED = "CURRENT_PASSWORD_REQUIRED"
    INVALID_CURRENT_PASSWORD = "INVALID_CURRENT_PASSWORD"

    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"

    COLUMN_NOT_FOUND = "COLUMN_NOT_FOUND"
    COLUMN_BELONGS_ANOTHER_PROJECT = "COLUMN_BELONGS_ANOTHER_PROJECT"
    COLUMN_TASK_LIMIT_REACHED = "COLUMN_TASK_LIMIT_REACHED"
    ASSIGNEE_NOT_PROJECT_MEMBER = "ASSIGNEE_NOT_PROJECT_MEMBER"
    INVALID_TAG_IDS = "INVALID_TAG_IDS"
    INVALID_TARGET_COLUMN = "INVALID_TARGET_COLUMN"
    ANCHOR_TASK_NOT_FOUND = "ANCHOR_TASK_NOT_FOUND"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    MEMBERS_ONLY_OWN_TASKS = "MEMBERS_ONLY_OWN_TASKS"

    TAG_ALREADY_EXISTS = "TAG_ALREADY_EXISTS"
    TAG_NOT_FOUND = "TAG_NOT_FOUND"

    INVITATION_NOT_FOUND = "INVITATION_NOT_FOUND"
    INVITATION_EXPIRED = "INVITATION_EXPIRED"
    INVITATION_USAGE_LIMIT_REACHED = "INVITATION_USAGE_LIMIT_REACHED"
    INVITATION_FOR_OTHER_EMAIL = "INVITATION_FOR_OTHER_EMAIL"

    MEMBER_NOT_FOUND = "MEMBER_NOT_FOUND"
    NOT_A_PROJECT_MEMBER = "NOT_A_PROJECT_MEMBER"
    CANNOT_REMOVE_OWNER = "CANNOT_REMOVE_OWNER"
    MANAGERS_CANNOT_REMOVE = "MANAGERS_CANNOT_REMOVE"
    CANNOT_CHANGE_OWNER_ROLE = "CANNOT_CHANGE_OWNER_ROLE"

    DATABASE_ERROR = "DATABASE_ERROR"
    FILE_UPLOAD_FAILED = "FILE_UPLOAD_FAILED"
    DB_COMMIT_FAILED = "DB_COMMIT_FAILED"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    INVALID_FILE_TYPE = "INVALID_FILE_TYPE"

    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class SuccessCode(StrEnum):
    ALREADY_PROJECT_MEMBER = "ALREADY_PROJECT_MEMBER"
    INVITATION_ACCEPT_SUCCESS = "INVITATION_ACCEPT_SUCCESS"


def error_response(
    code: ErrorCode | str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": str(code),
        }
    }
    if params:
        payload["error"]["params"] = params
    return payload


def normalize_error_detail(detail: Any) -> dict[str, Any]:
    if isinstance(detail, dict):
        nested_error = detail.get("error")
        if isinstance(nested_error, dict) and isinstance(nested_error.get("code"), str):
            return detail

        code = detail.get("code")
        params = detail.get("params")
        if isinstance(code, (str, ErrorCode)):
            return error_response(
                code=str(code),
                params=params if isinstance(params, dict) else None,
            )

    if isinstance(detail, ErrorCode):
        return error_response(detail)

    if isinstance(detail, str) and _ERROR_CODE_RE.match(detail):
        return error_response(detail)

    return error_response(ErrorCode.UNKNOWN_ERROR)
