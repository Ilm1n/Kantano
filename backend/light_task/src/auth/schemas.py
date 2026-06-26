from src.schemas import BaseSchema


class Token(BaseSchema):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseSchema):
    sub: str
    type: str
    username: str | None = None
    email: str | None = None


class UserPayload(BaseSchema):
    sub: int
    username: str
    email: str
    is_active: bool = True
