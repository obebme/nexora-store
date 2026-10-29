import pytest
from nexora_backend.config import Settings
from pydantic import ValidationError

PRODUCTION_SETTINGS = {
    "database_url": "postgresql+psycopg://user:password@db/nexora",
    "environment": "production",
    "jwt_secret": "local-test-secret-012345678901234567890123456789",
    "frontend_origins": ["https://shop.example"],
    "email_verification_base_url": "https://shop.example",
    "google_oauth_redirect_uri": None,
    "smtp_host": "smtp.example.com",
    "smtp_username": "shop",
    "smtp_password": "test-password",
    "smtp_from_email": "orders@example.com",
    "sales_enabled": False,
}


def test_production_settings_accept_secure_urls_and_postgresql():
    settings = Settings(**PRODUCTION_SETTINGS)
    assert settings.environment == "production"
    assert settings.order_reservation_minutes == 30


@pytest.mark.parametrize(
    "changes",
    [
        {"frontend_origins": ["http://shop.example"]},
        {"database_url": "sqlite:///local.db"},
        {"smtp_password": None},
    ],
)
def test_production_settings_reject_insecure_or_incomplete_configuration(changes):
    with pytest.raises(ValidationError):
        Settings(**(PRODUCTION_SETTINGS | changes))


def test_payment_credentials_must_be_configured_as_a_pair():
    with pytest.raises(ValidationError):
        Settings(
            database_url=PRODUCTION_SETTINGS["database_url"],
            jwt_secret=PRODUCTION_SETTINGS["jwt_secret"],
            yookassa_shop_id="shop-id",
            yookassa_secret_key="",
        )


def test_sales_cannot_be_enabled_without_payment_credentials():
    with pytest.raises(ValidationError):
        Settings(
            database_url=PRODUCTION_SETTINGS["database_url"],
            jwt_secret=PRODUCTION_SETTINGS["jwt_secret"],
            sales_enabled=True,
        )


@pytest.mark.parametrize("minutes", [4, 121])
def test_order_reservation_timeout_is_bounded(minutes: int):
    with pytest.raises(ValidationError):
        Settings(
            database_url=PRODUCTION_SETTINGS["database_url"],
            jwt_secret=PRODUCTION_SETTINGS["jwt_secret"],
            order_reservation_minutes=minutes,
        )
