from pathlib import Path
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NEXORA API"
    database_url: str
    environment: str = "development"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    frontend_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    uploads_dir: Path | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_ssl: bool = False
    smtp_starttls: bool = True
    email_verification_base_url: str = "http://localhost:5173"
    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None
    yookassa_return_url: str = "http://localhost:5173/payment/return"
    order_reservation_minutes: int = 30
    sales_enabled: bool = False
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_runtime_configuration(self) -> Settings:
        if (
            len(self.jwt_secret.strip()) < 32
            or self.jwt_secret.strip().lower() == "replace-with-a-long-random-secret"
        ):
            raise ValueError("Задайте уникальный случайный JWT_SECRET длиной не менее 32 символов")
        if bool(self.yookassa_shop_id) != bool(self.yookassa_secret_key):
            raise ValueError("Укажите обе настройки ЮKassa или оставьте обе пустыми")
        if self.sales_enabled and not self.yookassa_shop_id:
            raise ValueError("Нельзя включить приём заказов без настроенных реквизитов ЮKassa")
        if not 5 <= self.order_reservation_minutes <= 120:
            raise ValueError("Срок резерва заказа должен быть от 5 до 120 минут")
        if self.smtp_use_ssl and self.smtp_starttls:
            raise ValueError("Выберите один режим SMTP: SSL или STARTTLS")
        if self.environment == "production":
            secure_urls = [*self.frontend_origins, self.email_verification_base_url]
            if self.google_oauth_redirect_uri:
                secure_urls.append(self.google_oauth_redirect_uri)
            if self.yookassa_shop_id:
                secure_urls.append(self.yookassa_return_url)
            if any(
                urlsplit(url).scheme != "https" or not urlsplit(url).netloc for url in secure_urls
            ):
                raise ValueError("В production все публичные URL должны использовать HTTPS")
            if self.database_url.startswith("sqlite"):
                raise ValueError("В production необходимо использовать PostgreSQL")
            if not all(
                (self.smtp_host, self.smtp_username, self.smtp_password, self.smtp_from_email)
            ):
                raise ValueError("В production необходимо настроить SMTP для писем магазина")
        return self


settings = Settings()
