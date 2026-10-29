import smtplib
from email.message import EmailMessage
from html import escape
from urllib.parse import quote

from .config import settings


class EmailDeliveryError(Exception):
    pass


def _send_email(recipient: str, subject: str, text_body: str, html_body: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise EmailDeliveryError("Почтовый сервер не настроен")
    if bool(settings.smtp_username) != bool(settings.smtp_password):
        raise EmailDeliveryError("Для SMTP нужны и имя пользователя, и пароль")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"NEXORA <{settings.smtp_from_email}>"
    message["To"] = recipient
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise EmailDeliveryError("Не удалось отправить письмо") from error


def send_verification_email(recipient: str, token: str) -> None:
    link = (
        f"{settings.email_verification_base_url.rstrip('/')}/email/verified"
        f"?token={quote(token, safe='')}"
    )
    safe_link = escape(link, quote=True)
    safe_email = escape(recipient)
    _send_email(
        recipient,
        "Подтвердите email — NEXORA",
        (
            f"Привет!\n\nСпасибо за регистрацию в NEXORA. "
            f"Подтвердите адрес {recipient}, перейдя по ссылке:\n{link}\n\n"
            "Ссылка действует 24 часа. Если вы не создавали аккаунт, просто "
            "проигнорируйте это письмо."
        ),
        (
            '<!doctype html><html lang="ru"><body style="margin:0;background:#11120f;'
            'color:#f3f0e8;font-family:Arial,sans-serif;padding:32px">'
            '<main style="max-width:560px;margin:auto;border:1px solid #34362e;padding:36px">'
            '<p style="color:#c7f36a;letter-spacing:5px;font-weight:bold">NEXORA</p>'
            '<h1 style="font-size:34px;line-height:1.05">ТВОЙ ГОРОД.<br>ТВОЙ АККАУНТ.</h1>'
            f"<p>Привет! Спасибо, что присоединился к NEXORA. Подтверди адрес "
            f"<strong>{safe_email}</strong>, чтобы открыть историю заказов.</p>"
            f'<p style="margin:30px 0"><a href="{safe_link}" style="background:#c7f36a;'
            'color:#11120f;padding:15px 20px;text-decoration:none;font-weight:bold">'
            "ПОДТВЕРДИТЬ EMAIL ↗</a></p>"
            '<p style="color:#aaa;font-size:13px">Ссылка действует 24 часа. '
            "Если вы не создавали аккаунт, проигнорируйте это письмо.</p>"
            "</main></body></html>"
        ),
    )


def send_email_verified_notice(recipient: str) -> None:
    safe_email = escape(recipient)
    _send_email(
        recipient,
        "Email подтверждён — NEXORA",
        (
            f"Адрес {recipient} успешно подтверждён. Теперь вы можете войти в "
            "аккаунт NEXORA и пользоваться историей заказов."
        ),
        (
            '<!doctype html><html lang="ru"><body style="margin:0;background:#11120f;'
            'color:#f3f0e8;font-family:Arial,sans-serif;padding:32px">'
            '<main style="max-width:560px;margin:auto;border:1px solid #34362e;padding:36px">'
            '<p style="color:#c7f36a;letter-spacing:5px;font-weight:bold">NEXORA</p>'
            '<div style="font-size:52px;color:#c7f36a">✓</div>'
            '<h1 style="font-size:34px">ПОЧТА ПОДТВЕРЖДЕНА.</h1>'
            f"<p>Адрес <strong>{safe_email}</strong> подтверждён. "
            "Рады видеть тебя в NEXORA.</p></main></body></html>"
        ),
    )


def send_password_reset_email(recipient: str, token: str) -> None:
    link = (
        f"{settings.email_verification_base_url.rstrip('/')}/account/reset-password"
        f"?token={quote(token, safe='')}"
    )
    safe_link = escape(link, quote=True)
    safe_email = escape(recipient)
    _send_email(
        recipient,
        "Сброс пароля — NEXORA",
        (
            f"Для адреса {recipient} запрошен сброс пароля NEXORA. "
            f"Создайте новый пароль по ссылке:\n{link}\n\n"
            "Ссылка действует 1 час. Если вы не запрашивали сброс, "
            "проигнорируйте это письмо."
        ),
        (
            '<!doctype html><html lang="ru"><body style="margin:0;background:#11120f;'
            'color:#f3f0e8;font-family:Arial,sans-serif;padding:32px">'
            '<main style="max-width:560px;margin:auto;border:1px solid #34362e;padding:36px">'
            '<p style="color:#c7f36a;letter-spacing:5px;font-weight:bold">NEXORA</p>'
            '<h1 style="font-size:34px">ВОССТАНОВЛЕНИЕ ДОСТУПА.</h1>'
            f"<p>Для адреса <strong>{safe_email}</strong> запрошен сброс пароля.</p>"
            f'<p style="margin:30px 0"><a href="{safe_link}" style="background:#c7f36a;'
            'color:#11120f;padding:15px 20px;text-decoration:none;font-weight:bold">'
            "СОЗДАТЬ НОВЫЙ ПАРОЛЬ ↗</a></p>"
            '<p style="color:#aaa;font-size:13px">Ссылка действует 1 час. '
            "Если вы не запрашивали сброс, проигнорируйте это письмо.</p>"
            "</main></body></html>"
        ),
    )
