import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "MIKHERB AI"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./mikherb.db")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "mikherb_ai_secret_key_dev_mode_12345")

    DATA_DIR: str = os.getenv("DATA_DIR", "./data")
    REPORTS_DIR: str = os.getenv("REPORTS_DIR", "./reports")

    class Config:
        case_sensitive = True

settings = Settings()
