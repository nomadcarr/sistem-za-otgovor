from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Claude AI
    anthropic_api_key: str

    # Email — за изпращане на дневния репорт
    email_address: str
    email_password: str
    email_smtp_server: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    report_recipient_email: str

    # Системни настройки
    inactivity_timeout_minutes: int = 60
    daily_report_time: str = "23:30"
    timezone: str = "Europe/Sofia"

    class Config:
        env_file = ".env"


settings = Settings()
