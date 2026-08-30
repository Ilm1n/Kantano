from pydantic import EmailStr, Field

from src.schemas import BaseSchema


class RegistrationRequest(BaseSchema):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr


class ResendVerificationRequest(BaseSchema):
    email: EmailStr


class ConfirmRegistrationRequest(BaseSchema):
    token: str = Field(min_length=1)
    password: str = Field(min_length=8)


class VerificationTokenRequest(BaseSchema):
    token: str = Field(min_length=1)


class RegistrationAccepted(BaseSchema):
    detail: str = "CHECK_YOUR_EMAIL"


class EmailConfirmed(BaseSchema):
    detail: str = "EMAIL_CONFIRMED"
