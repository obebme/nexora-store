from email.message import EmailMessage

import pytest
from nexora_backend import email_service


class FakeSMTP:
    sent_messages: list[EmailMessage] = []
    starttls_calls = 0
    login_calls: list[tuple[str, str]] = []

    def __init__(self, host: str, port: int, timeout: int):
        assert host == "smtp.example.com"
        assert port == 587
        assert timeout == 15

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def starttls(self):
        type(self).starttls_calls += 1

    def login(self, username: str, password: str):
        type(self).login_calls.append((username, password))

    def send_message(self, message: EmailMessage):
        type(self).sent_messages.append(message)


@pytest.mark.parametrize(
    "recipient",
    [
        "shopper@gmail.com",
        "shopper@outlook.com",
        "shopper@yahoo.com",
        "shopper@yandex.ru",
        "shopper@mail.ru",
        "shopper@list.ru",
        "shopper@inbox.ru",
        "shopper@bk.ru",
        "shopper@vk.com",
        "shopper@icloud.com",
        "shopper@rambler.ru",
    ],
)
def test_smtp_sends_confirmation_to_major_mail_domains(monkeypatch, recipient: str):
    FakeSMTP.sent_messages = []
    FakeSMTP.starttls_calls = 0
    FakeSMTP.login_calls = []
    monkeypatch.setattr(email_service.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(email_service.settings, "smtp_port", 587)
    monkeypatch.setattr(email_service.settings, "smtp_username", "smtp-user")
    monkeypatch.setattr(email_service.settings, "smtp_password", "smtp-password")
    monkeypatch.setattr(email_service.settings, "smtp_from_email", "shop@example.com")
    monkeypatch.setattr(email_service.settings, "smtp_use_ssl", False)
    monkeypatch.setattr(email_service.settings, "smtp_starttls", True)
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)

    email_service.send_verification_email(recipient, "verification-token")

    assert len(FakeSMTP.sent_messages) == 1
    assert FakeSMTP.sent_messages[0]["To"] == recipient
    assert FakeSMTP.starttls_calls == 1
    assert FakeSMTP.login_calls == [("smtp-user", "smtp-password")]


def test_smtp_ssl_mode_sends_without_starttls(monkeypatch):
    FakeSMTP.sent_messages = []
    FakeSMTP.starttls_calls = 0
    monkeypatch.setattr(email_service.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(email_service.settings, "smtp_port", 587)
    monkeypatch.setattr(email_service.settings, "smtp_username", None)
    monkeypatch.setattr(email_service.settings, "smtp_password", None)
    monkeypatch.setattr(email_service.settings, "smtp_from_email", "shop@example.com")
    monkeypatch.setattr(email_service.settings, "smtp_use_ssl", True)
    monkeypatch.setattr(email_service.settings, "smtp_starttls", True)
    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", FakeSMTP)

    email_service.send_email_verified_notice("shopper@icloud.com")

    assert len(FakeSMTP.sent_messages) == 1
    assert FakeSMTP.sent_messages[0]["To"] == "shopper@icloud.com"
    assert FakeSMTP.starttls_calls == 0
