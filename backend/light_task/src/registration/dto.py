from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class StartRegistrationCommand:
    username: str
    email: str
    client_ip: str


@dataclass(frozen=True, kw_only=True)
class ResendVerificationCommand:
    email: str
    client_ip: str


@dataclass(frozen=True, kw_only=True)
class ConfirmRegistrationCommand:
    token: str
    password: str


@dataclass(frozen=True, kw_only=True)
class ValidateRegistrationTokenCommand:
    token: str
