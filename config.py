from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Claude AI — единственото задължително поле
    anthropic_api_key: str

    # Email — незадължително, нужно само за дневния репорт
    email_address: Optional[str] = None
    email_password: Optional[str] = None
    email_smtp_server: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    report_recipient_email: Optional[str] = None

    # Системни настройки
    inactivity_timeout_minutes: int = 60
    daily_report_time: str = "23:30"
    timezone: str = "Europe/Sofia"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
