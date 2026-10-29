import base64
import json
from decimal import Decimal
from io import BytesIO
from urllib.request import Request

import pytest
from nexora_backend import payment_service


def test_create_payment_sends_basic_auth_idempotency_and_server_amount(monkeypatch):
    monkeypatch.setattr(payment_service.settings, "yookassa_shop_id", "shop-123")
    monkeypatch.setattr(payment_service.settings, "yookassa_secret_key", "secret-value")
    captured: dict[str, Request] = {}

    class Response(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def fake_urlopen(request: Request, timeout: int):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response(b'{"id":"payment-123"}')

    monkeypatch.setattr(payment_service, "urlopen", fake_urlopen)
    result = payment_service.create_payment(
        order_id=12,
        amount=Decimal("12990.00"),
        currency="RUB",
        description="NEXORA order 12",
        idempotence_key="stable-key",
    )

    request = captured["request"]
    assert request.full_url == "https://api.yookassa.ru/v3/payments"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == (
        "Basic " + base64.b64encode(b"shop-123:secret-value").decode("ascii")
    )
    assert request.get_header("Idempotence-key") == "stable-key"
    assert json.loads(request.data) == {
        "amount": {"value": "12990.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": payment_service.settings.yookassa_return_url,
        },
        "description": "NEXORA order 12",
        "metadata": {"order_id": "12"},
    }
    assert result == {"id": "payment-123"}


@pytest.mark.parametrize(
    ("operation", "expected_url", "expected_payload"),
    [
        (
            "cancel",
            "https://api.yookassa.ru/v3/payments/payment-123/cancel",
            {},
        ),
        (
            "refund",
            "https://api.yookassa.ru/v3/refunds",
            {
                "payment_id": "payment-123",
                "amount": {"value": "12990.00", "currency": "RUB"},
                "description": "NEXORA return",
            },
        ),
    ],
)
def test_cancel_and_refund_requests_are_idempotent(
    monkeypatch, operation: str, expected_url: str, expected_payload: dict
):
    monkeypatch.setattr(payment_service.settings, "yookassa_shop_id", "shop-123")
    monkeypatch.setattr(payment_service.settings, "yookassa_secret_key", "secret-value")
    captured: dict[str, Request] = {}

    class Response(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def fake_urlopen(request: Request, timeout: int):
        captured["request"] = request
        return Response(b'{"id":"result-123","status":"canceled"}')

    monkeypatch.setattr(payment_service, "urlopen", fake_urlopen)
    if operation == "cancel":
        payment_service.cancel_payment("payment-123", "cancel-key")
        expected_key = "cancel-key"
    else:
        payment_service.create_refund(
            payment_id="payment-123",
            amount=Decimal("12990.00"),
            currency="RUB",
            description="NEXORA return",
            idempotence_key="refund-key",
        )
        expected_key = "refund-key"

    request = captured["request"]
    assert request.full_url == expected_url
    assert request.get_method() == "POST"
    assert request.get_header("Idempotence-key") == expected_key
    assert json.loads(request.data) == expected_payload
