import base64
import json
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import settings

YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"
YOOKASSA_REFUNDS_URL = "https://api.yookassa.ru/v3/refunds"
REQUEST_TIMEOUT_SECONDS = 10


class YooKassaError(Exception):
    pass


def _authorization_header() -> str:
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        raise YooKassaError("ЮKassa не настроена")
    credentials = f"{settings.yookassa_shop_id}:{settings.yookassa_secret_key}".encode()
    return f"Basic {base64.b64encode(credentials).decode('ascii')}"


def _request(
    method: str,
    url: str,
    *,
    payload: dict | None = None,
    idempotence_key: str | None = None,
) -> dict:
    headers = {
        "Authorization": _authorization_header(),
        "Accept": "application/json",
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode()
    if idempotence_key is not None:
        headers["Idempotence-Key"] = idempotence_key
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read())
    except HTTPError as error:
        raise YooKassaError(f"ЮKassa отклонила запрос (HTTP {error.code})") from None
    except URLError, TimeoutError, json.JSONDecodeError:
        raise YooKassaError("Не удалось связаться с ЮKassa") from None
    if not isinstance(result, dict):
        raise YooKassaError("ЮKassa вернула неожиданный ответ")
    return result


def create_payment(
    *,
    order_id: int,
    amount: Decimal,
    currency: str,
    description: str,
    idempotence_key: str,
) -> dict:
    return _request(
        "POST",
        YOOKASSA_API_URL,
        idempotence_key=idempotence_key,
        payload={
            "amount": {"value": f"{amount:.2f}", "currency": currency},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": settings.yookassa_return_url,
            },
            "description": description[:128],
            "metadata": {"order_id": str(order_id)},
        },
    )


def get_payment(payment_id: str) -> dict:
    return _request("GET", f"{YOOKASSA_API_URL}/{quote(payment_id, safe='')}")


def cancel_payment(payment_id: str, idempotence_key: str) -> dict:
    return _request(
        "POST",
        f"{YOOKASSA_API_URL}/{quote(payment_id, safe='')}/cancel",
        idempotence_key=idempotence_key,
        payload={},
    )


def create_refund(
    *,
    payment_id: str,
    amount: Decimal,
    currency: str,
    description: str,
    idempotence_key: str,
) -> dict:
    return _request(
        "POST",
        YOOKASSA_REFUNDS_URL,
        idempotence_key=idempotence_key,
        payload={
            "payment_id": payment_id,
            "amount": {"value": f"{amount:.2f}", "currency": currency},
            "description": description[:128],
        },
    )


def get_refund(refund_id: str) -> dict:
    return _request("GET", f"{YOOKASSA_REFUNDS_URL}/{quote(refund_id, safe='')}")
