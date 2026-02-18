from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database — SQLite by default, swap to PostgreSQL via env
    DATABASE_URL: str = "sqlite:///./cs2analytics.db"

    # Security
    API_KEY: str = "changeme-set-in-dotenv"
    API_KEY_ENABLED: bool = True

    # App
    APP_TITLE: str = "CS2 Analytics Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Upload
    MAX_DEMO_SIZE_MB: int = 500

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
