from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "FastAPI Auth"
    debug: bool = False

    # Database
    db_user: str = "root"
    db_password: str = "root"
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "app_db"

    @property
    def database_url(self) -> str:
        password = quote_plus(self.db_password)
        return f"mysql+aiomysql://{self.db_user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"

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
