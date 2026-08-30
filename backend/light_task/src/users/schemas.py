from pydantic import EmailStr, Field, field_validator

from src.schemas import BaseSchema


class UserBase(BaseSchema):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr


class UserRead(UserBase):
    id: int
    is_active: bool
    has_password: bool
    full_name: str | None = Field(None, min_length=1, max_length=255)
    avatar_url: str | None = Field(None, max_length=512)


class UserUpdate(BaseSchema):
    username: str | None = Field(None, min_length=1, max_length=50)
    full_name: str | None = Field(None, min_length=1, max_length=255)

    @field_validator("full_name", mode="before")
    @classmethod
    def normalize_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


class UserPasswordUpdate(BaseSchema):
    current_password: str | None = Field(None, min_length=8)
    new_password: str = Field(min_length=8)


class UserPublic(BaseSchema):
    id: int
    username: str
    full_name: str | None
    avatar_url: str | None


class UserCollaborator(UserPublic):
    email: EmailStr
