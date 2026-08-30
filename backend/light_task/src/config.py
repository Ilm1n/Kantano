from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, PostgresDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class RunConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:4173",
        "http://127.0.0.1:5173",
    ]


class InvitationConfig(BaseModel):
    base_url: str = "http://localhost:5173/invite"


class FrontendConfig(BaseModel):
    base_url: str = "http://localhost:5173"


class ResendConfig(BaseModel):
    base_url: str = "https://api.resend.com"
    api_key: str = ""
    from_email: str = "no-reply@kantano.ru"
    from_name: str = "Kantano"


class EmailConfig(BaseModel):
    provider: Literal["resend"] = "resend"


class QueueConfig(BaseModel):
    host: str = "localhost"
    port: int = 5672
    user: str = "lighttask"
    password: str = "lighttask-dev"  # noqa: S105
    virtual_host: str = "kantano"

    @computed_field
    @property
    def broker_url(self) -> str:
        virtual_host = "/" if self.virtual_host == "/" else quote(self.virtual_host, safe="")
        return (
            f"amqp://{quote(self.user, safe='')}:{quote(self.password, safe='')}"
            f"@{self.host}:{self.port}/{virtual_host}"
        )


class RegistrationConfig(BaseModel):
    verification_ttl_hours: int = 24
    resend_cooldown_seconds: int = 60
    max_emails_per_hour: int = 3
    max_requests_per_ip_hour: int = 10


class YandexConfig(BaseModel):
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://localhost:8000/api/auth/yandex/callback"
    authorize_url: str = "https://oauth.yandex.ru/authorize"
    token_url: str = "https://oauth.yandex.ru/token"  # noqa: S105
    userinfo_url: str = "https://login.yandex.ru/info"
    state_cookie_name: str = "yandex_oauth_state"
    state_cookie_max_age_seconds: int = 10 * 60


class DatabaseConfig(BaseModel):
    user: str
    password: str
    host: str = "localhost"
    port: int = 5432
    name: str

    echo: bool = False
    echo_pool: bool = False
    pool_size: int = 50
    max_overflow: int = 10

    naming_convention: dict[str, str] = {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }

    @computed_field
    @property
    def url(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            path=self.name,
        )


class AuthJWT(BaseModel):
    private_key_path: Path = BASE_DIR / "certs" / "jwt-private.pem"
    public_key_path: Path = BASE_DIR / "certs" / "jwt-public.pem"
    algorithm: str = "RS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    secure: bool = True


class S3Config(BaseModel):
    backend: Literal["local", "s3"] = "local"
    access_key: str = ""
    secret_key: str = ""
    bucket_name: str = ""
    endpoint_url: str = "https://s3.ru1.storage.beget.cloud"
    region_name: str = "ru1"
    local_storage_dir: Path = BASE_DIR / ".local" / "avatar-storage"
    local_public_url: str = "http://localhost:8000/local-storage"

    @model_validator(mode="after")
    def validate_s3_credentials(self) -> "S3Config":
        if self.backend == "s3" and (
            not self.access_key or not self.secret_key or not self.bucket_name
        ):
            raise ValueError(
                "S3 credentials and bucket name are required when S3 backend is enabled"
            )
        return self


class Files(BaseModel):
    avatar_max_size: int = 5 * 1024 * 1024  # 5 MB
    avatar_allowed_types: list[str] = ["image/jpeg", "image/png", "image/webp"]


class RealtimeConfig(BaseModel):
    redis_url: str = "redis://localhost:6379/0"
    redis_channel: str = "realtime.v1.events"
    ws_auth_timeout_seconds: int = 10
    presence_ttl_seconds: int = 30
    presence_sync_interval_seconds: int = 10
    presence_key_prefix: str = "realtime:v1:presence"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR.parent.parent / ".env",),
        case_sensitive=False,
        env_nested_delimiter="__",
        env_prefix="LIGHTTASK_CONFIG__",
        extra="ignore",
    )
    run: RunConfig = RunConfig()
    db: DatabaseConfig
    auth_jwt: AuthJWT = AuthJWT()
    invite: InvitationConfig = InvitationConfig()
    frontend: FrontendConfig = FrontendConfig()
    email: EmailConfig = EmailConfig()
    resend: ResendConfig = ResendConfig()
    queue: QueueConfig = QueueConfig()
    registration: RegistrationConfig = RegistrationConfig()
    yandex: YandexConfig = YandexConfig()
    s3: S3Config
    files: Files = Files()
    realtime: RealtimeConfig = RealtimeConfig()


settings = Settings()  # type: ignore[call-arg]
