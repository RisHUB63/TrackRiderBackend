from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "FastAPI Auth"
    debug: bool = False

    # Database — full URL takes priority, fallback to individual creds
    database_url: str | None = None
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "app_db"

    @property
    def db_url(self) -> str:
        if self.database_url:
            url = self.database_url
            # Convert postgres:// to postgresql+asyncpg:// for async driver
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            return url
        password = quote_plus(self.db_password)
        return f"postgresql+asyncpg://{self.db_user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"

    # JWT
    jwt_secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # WebSocket
    ws_token_expire_minutes: int = 5

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0


settings = Settings()
