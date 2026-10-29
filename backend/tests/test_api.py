import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from nexora_backend import main as backend_main
from nexora_backend.database import Base, get_db
from nexora_backend.main import app
from nexora_backend.models import Category, Order, Product, User
from nexora_backend.schemas import GoogleCodeExchange, ProductCreate, ProductUpdate
from nexora_backend.security import hash_password
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(backend_main.settings, "sales_enabled", True)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    verification_tokens: dict[str, str] = {}
    sent_notices: list[str] = []
    password_reset_tokens: dict[str, str] = {}
    monkeypatch.setattr(
        backend_main,
        "send_verification_email",
        lambda email, token: verification_tokens.__setitem__(email, token),
    )
    monkeypatch.setattr(
        backend_main, "send_email_verified_notice", lambda email: sent_notices.append(email)
    )
    monkeypatch.setattr(
        backend_main,
        "send_password_reset_email",
        lambda email, token: password_reset_tokens.__setitem__(email, token),
    )
    with TestingSession.begin() as db:
        category = Category(name="Обувь", slug="shoes", description="Обувь")
        db.add(category)
        db.flush()
        db.add(
            Product(
                category_id=category.id,
                sku="NX-SHO-001",
                name="RIFT RUNNER 02",
                slug="rift-runner-02",
                description="Кроссовки",
                price="12990.00",
                currency_code="RUB",
                stock_quantity=3,
                image_url="https://example.com/shoe.jpg",
                color_name="Графит",
                sizes=["40", "41"],
                is_active=True,
            )
        )
        db.add(
            User(
                email="admin@example.com",
                password_hash=hash_password("test-admin-password"),
                role="admin",
            )
        )
    with TestClient(app) as test_client:
        test_client.verification_tokens = verification_tokens
        test_client.sent_notices = sent_notices
        test_client.password_reset_tokens = password_reset_tokens
        test_client.testing_session = TestingSession
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def register(client: TestClient, email: str = "buyer@example.com") -> str:
    response = client.post(
        "/api/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )
    assert response.status_code == 201
    token = client.verification_tokens[email]
    verified = client.get("/api/auth/verify-email", params={"token": token})
    assert verified.status_code == 200
    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def test_catalog_is_public_and_filterable(client: TestClient):
    response = client.get("/api/products", params={"category": "shoes", "sort": "price_asc"})
    assert response.status_code == 200
    assert response.json()[0]["sizes"] == ["40", "41"]
    assert response.json()[0]["price"] == "12990.00"
    assert response.json()[0]["stock_by_size"] == {"40": 2, "41": 1}


def test_catalog_prices_are_limited_to_rubles():
    with pytest.raises(ValidationError):
        ProductCreate(
            category_id=1,
            sku="NX-TEST-001",
            name="Test product",
            slug="test-product",
            price=100,
            currency_code="USD",
        )
    with pytest.raises(ValidationError):
        ProductUpdate(currency_code="EUR")


def test_registration_requires_email_verification_before_login(client: TestClient):
    registration = client.post(
        "/api/auth/register",
        json={"email": "new-buyer@example.com", "password": "correct-horse-battery"},
    )
    assert registration.status_code == 201
    assert "Подтверди email" in registration.json()["message"]
    assert "new-buyer@example.com" in client.verification_tokens

    login = client.post(
        "/api/auth/login",
        json={"email": "new-buyer@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 403
    assert "подтверди email" in login.json()["detail"]


def test_email_verification_is_one_time_and_sends_a_confirmation_notice(client: TestClient):
    registration = client.post(
        "/api/auth/register",
        json={"email": "verified@example.com", "password": "correct-horse-battery"},
    )
    assert registration.status_code == 201
    token = client.verification_tokens["verified@example.com"]

    verified = client.get("/api/auth/verify-email", params={"token": token})
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    assert verified.json()["notification_sent"] is True
    assert client.sent_notices == ["verified@example.com"]

    login = client.post(
        "/api/auth/login",
        json={"email": "verified@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    repeated = client.get("/api/auth/verify-email", params={"token": token})
    assert repeated.status_code == 400


def test_password_reset_changes_password_and_consumes_link(client: TestClient):
    register(client, "reset-user@example.com")
    request = client.post(
        "/api/auth/password-reset/request", json={"email": "reset-user@example.com"}
    )
    assert request.status_code == 200
    token = client.password_reset_tokens["reset-user@example.com"]

    reset = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "new_password": "new-correct-password"},
    )
    assert reset.status_code == 200
    assert "обновлён" in reset.json()["message"]
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "reset-user@example.com", "password": "correct-horse-battery"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "reset-user@example.com", "password": "new-correct-password"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "new_password": "another-correct-password"},
        ).status_code
        == 400
    )


def test_password_reset_request_does_not_disclose_unknown_email(client: TestClient):
    register(client, "known-reset-user@example.com")
    existing = client.post(
        "/api/auth/password-reset/request", json={"email": "known-reset-user@example.com"}
    )
    missing = client.post("/api/auth/password-reset/request", json={"email": "nobody@example.com"})
    assert existing.status_code == missing.status_code == 200
    assert existing.json() == missing.json()


def test_resending_email_invalidates_the_previous_verification_link(client: TestClient):
    client.post(
        "/api/auth/register",
        json={"email": "resend@example.com", "password": "correct-horse-battery"},
    )
    first_token = client.verification_tokens["resend@example.com"]
    resent = client.post("/api/auth/resend-verification", json={"email": "resend@example.com"})
    assert resent.status_code == 200
    second_token = client.verification_tokens["resend@example.com"]
    assert second_token != first_token
    assert client.get("/api/auth/verify-email", params={"token": first_token}).status_code == 400
    assert client.get("/api/auth/verify-email", params={"token": second_token}).status_code == 200


def test_registration_surfaces_mail_delivery_failure_and_allows_resend(
    client: TestClient, monkeypatch
):
    def fail_delivery(_email: str, _token: str) -> None:
        raise backend_main.EmailDeliveryError("Почта не настроена")

    monkeypatch.setattr(backend_main, "send_verification_email", fail_delivery)
    registration = client.post(
        "/api/auth/register",
        json={"email": "mail-failure@example.com", "password": "correct-horse-battery"},
    )
    assert registration.status_code == 503
    assert "Аккаунт создан" in registration.json()["detail"]
    login = client.post(
        "/api/auth/login",
        json={"email": "mail-failure@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 403
    monkeypatch.setattr(
        backend_main,
        "send_verification_email",
        lambda email, token: client.verification_tokens.__setitem__(email, token),
    )
    resent = client.post(
        "/api/auth/resend-verification", json={"email": "mail-failure@example.com"}
    )
    assert resent.status_code == 200
    assert "mail-failure@example.com" in client.verification_tokens


def test_cart_rejects_invalid_size_and_tracks_selected_size(client: TestClient):
    token = register(client)
    headers = {"Authorization": f"Bearer {token}"}
    invalid = client.post(
        "/api/cart/items",
        headers=headers,
        json={"product_id": 1, "selected_size": "45", "quantity": 1},
    )
    assert invalid.status_code == 422
    added = client.post(
        "/api/cart/items",
        headers=headers,
        json={"product_id": 1, "selected_size": "40", "quantity": 2},
    )
    assert added.status_code == 200
    assert added.json()["items"][0]["selected_size"] == "40"
    assert added.json()["total_amount"] == "25980.00"


def test_cart_quantity_cannot_exceed_available_stock(client: TestClient):
    token = register(client)
    headers = {"Authorization": f"Bearer {token}"}
    over_add = client.post(
        "/api/cart/items",
        headers=headers,
        json={"product_id": 1, "selected_size": "40", "quantity": 4},
    )
    assert over_add.status_code == 409

    client.post(
        "/api/cart/items",
        headers=headers,
        json={"product_id": 1, "selected_size": "40", "quantity": 2},
    )
    over_update = client.patch(
        "/api/cart/items/1/40",
        headers=headers,
        params={"quantity": 4},
    )
    assert over_update.status_code == 409


def test_inventory_is_reserved_independently_for_each_size(client: TestClient):
    admin = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "test-admin-password"}
    )
    admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    updated = client.patch(
        "/api/admin/products/1",
        headers=admin_headers,
        json={"stock_by_size": {"40": 1, "41": 2}},
    )
    assert updated.status_code == 200
    assert updated.json()["stock_quantity"] == 3

    buyer_headers = {"Authorization": f"Bearer {register(client)}"}
    first_size = client.post(
        "/api/cart/items",
        headers=buyer_headers,
        json={"product_id": 1, "selected_size": "40", "quantity": 1},
    )
    second_size = client.post(
        "/api/cart/items",
        headers=buyer_headers,
        json={"product_id": 1, "selected_size": "41", "quantity": 2},
    )
    exhausted_size = client.post(
        "/api/cart/items",
        headers=buyer_headers,
        json={"product_id": 1, "selected_size": "40", "quantity": 1},
    )
    assert first_size.status_code == 200
    assert second_size.status_code == 200
    assert exhausted_size.status_code == 409
    assert {
        line["selected_size"]: line["size_stock_quantity"] for line in second_size.json()["items"]
    } == {
        "40": 1,
        "41": 2,
    }
    checkout = client.post(
        "/api/orders",
        headers=buyer_headers,
        json={
            "shipping": {
                "name": "Test Buyer",
                "address_line1": "Test Street 1",
                "city": "Москва",
                "postal_code": "101000",
                "country_code": "RU",
            }
        },
    )
    assert checkout.status_code == 201
    after_checkout = client.get("/api/admin/products", headers=admin_headers).json()[0]
    assert after_checkout["stock_by_size"] == {"40": 0, "41": 0}
    cancellation = client.patch(
        f"/api/admin/orders/{checkout.json()['id']}/status",
        headers=admin_headers,
        json={"status": "cancelled"},
    )
    assert cancellation.status_code == 200
    restored = client.get("/api/admin/products", headers=admin_headers).json()[0]
    assert restored["stock_by_size"] == {"40": 1, "41": 2}


def test_cart_replace_checks_current_stock_and_returns_current_prices(client: TestClient):
    admin = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "test-admin-password"}
    )
    updated = client.patch(
        "/api/admin/products/1",
        headers={"Authorization": f"Bearer {admin.json()['access_token']}"},
        json={"price": "14000.00"},
    )
    assert updated.status_code == 200
    token = register(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.put(
        "/api/cart",
        headers=headers,
        json={"items": [{"product_id": 1, "selected_size": "40", "quantity": 1}]},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["unit_price"] == "14000.00"
    assert response.json()["items"][0]["size_stock_quantity"] == 2
    rejected = client.put(
        "/api/cart",
        headers=headers,
        json={"items": [{"product_id": 1, "selected_size": "40", "quantity": 4}]},
    )
    assert rejected.status_code == 409


def test_admin_can_save_product_gallery_and_customer_order_details(client: TestClient):
    admin = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "test-admin-password"}
    )
    admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    gallery = client.patch(
        "/api/admin/products/1",
        headers=admin_headers,
        json={
            "image_urls": ["https://example.com/front.jpg", "https://example.com/back.jpg"],
            "image_url": "https://example.com/front.jpg",
        },
    )
    assert gallery.status_code == 200
    assert gallery.json()["image_urls"] == [
        "https://example.com/front.jpg",
        "https://example.com/back.jpg",
    ]

    buyer_headers = {"Authorization": f"Bearer {register(client)}"}
    client.post(
        "/api/cart/items",
        headers=buyer_headers,
        json={"product_id": 1, "selected_size": "40", "quantity": 1},
    )
    created = client.post(
        "/api/orders",
        headers=buyer_headers,
        json={
            "shipping": {
                "name": "Test Buyer",
                "address_line1": "Test Street 1",
                "city": "Москва",
                "postal_code": "101000",
                "country_code": "RU",
                "phone": "+37360000000",
            }
        },
    )
    assert created.status_code == 201
    result = client.get(
        "/api/admin/orders",
        headers=admin_headers,
        params={"q": "buyer@example.com", "status": "pending"},
    )
    assert result.status_code == 200
    assert result.json()[0]["customer_email"] == "buyer@example.com"
    assert result.json()[0]["shipping_address_line1"] == "Test Street 1"
    assert result.json()[0]["shipping_phone"] == "+37360000000"


def test_checkout_snapshots_order_and_reserves_inventory(client: TestClient):
    token = register(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/cart/items",
        headers=headers,
        json={"product_id": 1, "selected_size": "41", "quantity": 1},
    )
    response = client.post(
        "/api/orders",
        headers=headers,
        json={
            "shipping": {
                "name": "Test Buyer",
                "address_line1": "Test Street 1",
                "city": "Москва",
                "postal_code": "101000",
                "country_code": "RU",
            }
        },
    )
    assert response.status_code == 201
    assert response.json()["payment_status"] == "pending"
    assert response.json()["items"][0]["selected_size"] == "41"
    assert response.json()["items"][0]["product_id"] == 1
    assert client.get("/api/cart", headers=headers).json()["items"] == []
    assert client.get("/api/products").json()[0]["stock_quantity"] == 2
    own_orders = client.get("/api/orders", headers=headers)
    assert own_orders.status_code == 200
    assert own_orders.json()[0]["items"][0]["product_id"] == 1


def test_checkout_rejects_shipping_outside_russia(client: TestClient):
    token = register(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/cart/items",
        headers=headers,
        json={"product_id": 1, "selected_size": "40", "quantity": 1},
    )
    response = client.post(
        "/api/orders",
        headers=headers,
        json={
            "shipping": {
                "name": "Test Buyer",
                "address_line1": "1 Test Street",
                "city": "Minsk",
                "postal_code": "220000",
                "country_code": "BY",
            }
        },
    )
    assert response.status_code == 422
    assert client.get("/api/products").json()[0]["stock_quantity"] == 3


def test_sales_gate_disables_checkout_without_reserving_stock(client: TestClient, monkeypatch):
    token = register(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/cart/items",
        headers=headers,
        json={"product_id": 1, "selected_size": "40", "quantity": 1},
    )
    monkeypatch.setattr(backend_main.settings, "sales_enabled", False)
    response = client.post(
        "/api/orders",
        headers=headers,
        json={
            "shipping": {
                "name": "Test Buyer",
                "address_line1": "1 Test Street",
                "city": "Moscow",
                "postal_code": "101000",
                "country_code": "RU",
            }
        },
    )
    assert response.status_code == 503
    assert "СДЭК" in response.json()["detail"]
    assert client.get("/api/products").json()[0]["stock_quantity"] == 3
    assert client.get("/api/payments/config").json()["checkout_available"] is False


def create_order_for_payment(client: TestClient) -> tuple[str, int]:
    token = register(client, "payment-buyer@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    added = client.post(
        "/api/cart/items",
        headers=headers,
        json={"product_id": 1, "selected_size": "40", "quantity": 1},
    )
    assert added.status_code == 200
    response = client.post(
        "/api/orders",
        headers=headers,
        json={
            "shipping": {
                "name": "Payment Buyer",
                "address_line1": "1 Test Street",
                "city": "Moscow",
                "postal_code": "101000",
                "country_code": "RU",
            }
        },
    )
    assert response.status_code == 201
    return token, response.json()["id"]


def test_order_payment_uses_server_total_and_is_idempotent(client: TestClient, monkeypatch):
    token, order_id = create_order_for_payment(client)
    monkeypatch.setattr(backend_main.settings, "yookassa_shop_id", "test-shop")
    monkeypatch.setattr(backend_main.settings, "yookassa_secret_key", "test-secret")
    calls = []

    def create_payment(**kwargs):
        calls.append(kwargs)
        return {
            "id": "payment-123",
            "confirmation": {"confirmation_url": "https://yookassa.test/confirm/123"},
        }

    monkeypatch.setattr(backend_main, "create_yookassa_payment", create_payment)
    monkeypatch.setattr(
        backend_main,
        "get_yookassa_payment",
        lambda payment_id: {
            "id": payment_id,
            "status": "pending",
            "amount": {"value": "12990.00", "currency": "RUB"},
            "metadata": {"order_id": str(order_id)},
        },
    )
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(f"/api/orders/{order_id}/payment", headers=headers)
    assert response.status_code == 200
    assert response.json()["confirmation_url"] == "https://yookassa.test/confirm/123"
    assert calls[0]["amount"] == Decimal("12990.00")
    assert calls[0]["currency"] == "RUB"
    assert calls[0]["order_id"] == order_id
    assert calls[0]["idempotence_key"]

    repeated = client.post(f"/api/orders/{order_id}/payment", headers=headers)
    assert repeated.status_code == 200
    assert repeated.json() == response.json()
    assert len(calls) == 1
    assert (
        client.post(
            f"/api/orders/{order_id}/payment",
            headers={"Authorization": f"Bearer {register(client, 'other@example.com')}"},
        ).status_code
        == 404
    )


def test_payment_creation_retry_reuses_idempotency_key(client: TestClient, monkeypatch):
    token, order_id = create_order_for_payment(client)
    monkeypatch.setattr(backend_main.settings, "yookassa_shop_id", "test-shop")
    monkeypatch.setattr(backend_main.settings, "yookassa_secret_key", "test-secret")
    keys = []

    def create_payment(**kwargs):
        keys.append(kwargs["idempotence_key"])
        if len(keys) == 1:
            raise backend_main.YooKassaError("temporary network failure")
        return {
            "id": "payment-after-retry",
            "confirmation": {"confirmation_url": "https://yookassa.test/confirm/retry"},
        }

    monkeypatch.setattr(backend_main, "create_yookassa_payment", create_payment)
    headers = {"Authorization": f"Bearer {token}"}

    failed = client.post(f"/api/orders/{order_id}/payment", headers=headers)
    assert failed.status_code == 502
    succeeded = client.post(f"/api/orders/{order_id}/payment", headers=headers)
    assert succeeded.status_code == 200
    assert keys[0] == keys[1]


def test_expired_unpaid_order_releases_reserved_inventory(client: TestClient):
    _, order_id = create_order_for_payment(client)
    expired_at = datetime.now(UTC) - timedelta(minutes=1)
    with client.testing_session.begin() as db:
        db.get(Order, order_id).reservation_expires_at = expired_at

    with client.testing_session() as db:
        assert backend_main.expire_unpaid_orders(db, now=datetime.now(UTC)) == 1

    with client.testing_session() as db:
        order = db.get(Order, order_id)
        assert order.status == "cancelled"
        assert order.payment_status == "failed"
    assert client.get("/api/products").json()[0]["stock_quantity"] == 3


def test_expired_order_cancels_pending_yookassa_payment_before_releasing_stock(
    client: TestClient, monkeypatch
):
    _, order_id = create_order_for_payment(client)
    with client.testing_session.begin() as db:
        order = db.get(Order, order_id)
        order.yookassa_payment_id = "payment-expiring"
        order.reservation_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    monkeypatch.setattr(
        backend_main,
        "get_yookassa_payment",
        lambda payment_id: {
            "id": payment_id,
            "status": "pending",
            "amount": {"value": "12990.00", "currency": "RUB"},
            "metadata": {"order_id": str(order_id)},
        },
    )
    cancellation_calls = []

    def cancel_payment(payment_id, idempotence_key):
        cancellation_calls.append((payment_id, idempotence_key))
        return {
            "id": payment_id,
            "status": "canceled",
            "amount": {"value": "12990.00", "currency": "RUB"},
            "metadata": {"order_id": str(order_id)},
        }

    monkeypatch.setattr(backend_main, "cancel_yookassa_payment", cancel_payment)
    with client.testing_session() as db:
        assert backend_main.expire_unpaid_orders(db, now=datetime.now(UTC)) == 1

    assert cancellation_calls[0][0] == "payment-expiring"
    assert cancellation_calls[0][1]
    with client.testing_session() as db:
        order = db.get(Order, order_id)
        assert order.status == "cancelled"
        assert order.payment_status == "failed"
        assert order.payment_cancel_idempotence_key == cancellation_calls[0][1]
    assert client.get("/api/products").json()[0]["stock_quantity"] == 3


def test_expired_order_with_successful_payment_keeps_inventory_reserved(
    client: TestClient, monkeypatch
):
    _, order_id = create_order_for_payment(client)
    with client.testing_session.begin() as db:
        order = db.get(Order, order_id)
        order.yookassa_payment_id = "payment-already-paid"
        order.reservation_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    monkeypatch.setattr(
        backend_main,
        "get_yookassa_payment",
        lambda payment_id: {
            "id": payment_id,
            "status": "succeeded",
            "amount": {"value": "12990.00", "currency": "RUB"},
            "metadata": {"order_id": str(order_id)},
        },
    )
    with client.testing_session() as db:
        assert backend_main.expire_unpaid_orders(db, now=datetime.now(UTC)) == 0

    with client.testing_session() as db:
        order = db.get(Order, order_id)
        assert order.status == "processing"
        assert order.payment_status == "paid"
    assert client.get("/api/products").json()[0]["stock_quantity"] == 2


def test_expired_order_with_unresolved_payment_keeps_inventory_reserved(
    client: TestClient, monkeypatch
):
    _, order_id = create_order_for_payment(client)
    with client.testing_session.begin() as db:
        order = db.get(Order, order_id)
        order.yookassa_payment_id = "payment-unresolved"
        order.reservation_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    monkeypatch.setattr(
        backend_main,
        "get_yookassa_payment",
        lambda payment_id: {
            "id": payment_id,
            "status": "waiting_for_capture",
            "amount": {"value": "12990.00", "currency": "RUB"},
            "metadata": {"order_id": str(order_id)},
        },
    )
    monkeypatch.setattr(
        backend_main,
        "cancel_yookassa_payment",
        lambda *_: pytest.fail("Unknown payment status must not trigger cancellation"),
    )
    with client.testing_session() as db:
        assert backend_main.expire_unpaid_orders(db, now=datetime.now(UTC)) == 0

    with client.testing_session() as db:
        order = db.get(Order, order_id)
        assert order.status == "pending"
        assert order.payment_status == "pending"
    assert client.get("/api/products").json()[0]["stock_quantity"] == 2


def test_yookassa_webhook_verifies_and_marks_paid_order(client: TestClient, monkeypatch):
    _, order_id = create_order_for_payment(client)
    with client.testing_session.begin() as db:
        order = db.get(Order, order_id)
        order.yookassa_payment_id = "payment-webhook"

    monkeypatch.setattr(
        backend_main,
        "get_yookassa_payment",
        lambda payment_id: {
            "id": payment_id,
            "status": "succeeded",
            "amount": {"value": "12990.00", "currency": "RUB"},
            "metadata": {"order_id": str(order_id)},
        },
    )
    response = client.post(
        "/api/payments/yookassa/webhook",
        json={"event": "payment.succeeded", "object": {"id": "payment-webhook"}},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    with client.testing_session() as db:
        order = db.get(Order, order_id)
        assert order.payment_status == "paid"
        assert order.status == "processing"


def test_admin_refund_waits_for_verified_yookassa_webhook(client: TestClient, monkeypatch):
    _, order_id = create_order_for_payment(client)
    with client.testing_session.begin() as db:
        order = db.get(Order, order_id)
        order.yookassa_payment_id = "payment-to-refund"
        order.payment_status = "paid"
        order.status = "processing"
    monkeypatch.setattr(backend_main.settings, "yookassa_shop_id", "test-shop")
    monkeypatch.setattr(backend_main.settings, "yookassa_secret_key", "test-secret")
    refund_calls = []

    def create_refund(**kwargs):
        refund_calls.append(kwargs)
        return {
            "id": "refund-123",
            "payment_id": "payment-to-refund",
            "status": "pending",
            "amount": {"value": "12990.00", "currency": "RUB"},
        }

    monkeypatch.setattr(backend_main, "create_yookassa_refund", create_refund)
    admin = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "test-admin-password"},
    )
    headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    response = client.post(f"/api/admin/orders/{order_id}/refund", headers=headers)
    assert response.status_code == 200
    assert response.json()["payment_status"] == "paid"
    assert response.json()["refund_status"] == "pending"
    assert refund_calls[0]["amount"] == Decimal("12990.00")
    assert refund_calls[0]["idempotence_key"]

    monkeypatch.setattr(
        backend_main,
        "get_yookassa_refund",
        lambda refund_id: {
            "id": refund_id,
            "payment_id": "payment-to-refund",
            "status": "succeeded",
            "amount": {"value": "12990.00", "currency": "RUB"},
        },
    )
    webhook = client.post(
        "/api/payments/yookassa/webhook",
        json={"event": "refund.succeeded", "object": {"id": "refund-123"}},
    )
    assert webhook.status_code == 200
    with client.testing_session() as db:
        order = db.get(Order, order_id)
        assert order.payment_status == "refunded"
        assert order.refund_status == "succeeded"
    assert client.get("/api/products").json()[0]["stock_quantity"] == 2


def test_yookassa_webhook_rejects_mismatched_amount(client: TestClient, monkeypatch):
    _, order_id = create_order_for_payment(client)
    with client.testing_session.begin() as db:
        db.get(Order, order_id).yookassa_payment_id = "payment-wrong-amount"

    monkeypatch.setattr(
        backend_main,
        "get_yookassa_payment",
        lambda payment_id: {
            "id": payment_id,
            "status": "succeeded",
            "amount": {"value": "1.00", "currency": "RUB"},
            "metadata": {"order_id": str(order_id)},
        },
    )
    response = client.post(
        "/api/payments/yookassa/webhook",
        json={"event": "payment.succeeded", "object": {"id": "payment-wrong-amount"}},
    )
    assert response.status_code == 400
    with client.testing_session() as db:
        assert db.get(Order, order_id).payment_status == "pending"


def test_admin_cannot_process_or_cancel_paid_orders_without_refund(client: TestClient):
    token = register(client)
    buyer_headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/cart/items",
        headers=buyer_headers,
        json={"product_id": 1, "selected_size": "40", "quantity": 1},
    )
    created = client.post(
        "/api/orders",
        headers=buyer_headers,
        json={
            "shipping": {
                "name": "Test Buyer",
                "address_line1": "Test Street 1",
                "city": "Moscow",
                "postal_code": "101000",
                "country_code": "RU",
            }
        },
    )
    assert created.status_code == 201

    admin = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "test-admin-password"},
    )
    admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}

    for next_status in ("processing", "shipped", "delivered"):
        response = client.patch(
            f"/api/admin/orders/{created.json()['id']}/status",
            headers=admin_headers,
            json={"status": next_status},
        )
        assert response.status_code == 409

    assert client.get("/api/products").json()[0]["stock_quantity"] == 2
    cancelled = client.patch(
        f"/api/admin/orders/{created.json()['id']}/status",
        headers=admin_headers,
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200
    assert client.get("/api/products").json()[0]["stock_quantity"] == 3


def test_admin_cannot_cancel_paid_order_without_refund(client: TestClient):
    token = register(client)
    buyer_headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/cart/items",
        headers=buyer_headers,
        json={"product_id": 1, "selected_size": "40", "quantity": 1},
    )
    created = client.post(
        "/api/orders",
        headers=buyer_headers,
        json={
            "shipping": {
                "name": "Test Buyer",
                "address_line1": "Test Street 1",
                "city": "Moscow",
                "postal_code": "101000",
                "country_code": "RU",
            }
        },
    )
    assert created.status_code == 201

    admin = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "test-admin-password"},
    )
    admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    with client.testing_session.begin() as db:
        order = db.get(Order, created.json()["id"])
        order.payment_status = "paid"
        db.commit()

    response = client.patch(
        f"/api/admin/orders/{created.json()['id']}/status",
        headers=admin_headers,
        json={"status": "cancelled"},
    )
    assert response.status_code == 409
    assert client.get("/api/products").json()[0]["stock_quantity"] == 2


def test_admin_routes_require_admin_role(client: TestClient):
    customer_token = register(client)
    customer = client.get(
        "/api/admin/orders", headers={"Authorization": f"Bearer {customer_token}"}
    )
    assert customer.status_code == 403
    customer_products = client.get(
        "/api/admin/products", headers={"Authorization": f"Bearer {customer_token}"}
    )
    assert customer_products.status_code == 403
    admin = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "test-admin-password"}
    )
    assert admin.status_code == 200
    admin_products = client.get(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {admin.json()['access_token']}"},
    )
    assert admin_products.status_code == 200
    assert admin_products.json()[0]["id"] == 1
    hidden = client.patch(
        "/api/admin/products/1",
        headers={"Authorization": f"Bearer {admin.json()['access_token']}"},
        json={"is_active": False},
    )
    assert hidden.status_code == 200
    assert (
        client.get(
            "/api/admin/products",
            headers={"Authorization": f"Bearer {admin.json()['access_token']}"},
        ).json()[0]["is_active"]
        is False
    )
    response = client.post(
        "/api/admin/products",
        headers={"Authorization": f"Bearer {admin.json()['access_token']}"},
        json={
            "category_id": 1,
            "sku": "NX-CLO-009",
            "name": "Test Tee",
            "slug": "test-tee",
            "price": "3000.00",
            "stock_quantity": 2,
            "sizes": ["S", "M"],
        },
    )
    assert response.status_code == 201


def test_admin_can_update_product_details(client: TestClient):
    admin = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "test-admin-password"}
    )
    headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    response = client.patch(
        "/api/admin/products/1",
        headers=headers,
        json={
            "name": "RIFT RUNNER UPDATED",
            "description": "Updated description",
            "price": "13990.00",
            "compare_at_price": "15990.00",
            "color_name": "Графит",
            "sizes": ["40", "42"],
            "image_url": "https://example.com/updated-shoe.jpg",
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "RIFT RUNNER UPDATED"
    assert response.json()["description"] == "Updated description"
    assert response.json()["price"] == "13990.00"
    assert response.json()["sizes"] == ["40", "42"]
    assert response.json()["image_url"] == "https://example.com/updated-shoe.jpg"


def test_admin_can_upload_product_image_and_use_it_on_product(client: TestClient):
    admin = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "test-admin-password"}
    )
    headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    image = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02\x00\x00\x00\x0bIDATx\xdac\xf8"
        b"\xff\x1f\x00\x03\x03\x02\x00\xef\xbf\xa5\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    upload = client.post(
        "/api/admin/uploads/images",
        headers={**headers, "Content-Type": "image/png"},
        content=image,
    )
    assert upload.status_code == 200
    image_url = upload.json()["image_url"]
    uploaded_file = backend_main.UPLOADS_DIR / image_url.rsplit("/", maxsplit=1)[-1]
    try:
        assert uploaded_file.read_bytes() == image
        served_image = client.get(image_url)
        assert served_image.status_code == 200
        assert served_image.content == image
        product = client.post(
            "/api/admin/products",
            headers=headers,
            json={
                "category_id": 1,
                "sku": "NX-CLO-010",
                "name": "Uploaded Tee",
                "slug": "uploaded-tee",
                "price": "3000.00",
                "image_url": image_url,
            },
        )
        assert product.status_code == 201
        assert product.json()["image_url"] == image_url
    finally:
        uploaded_file.unlink(missing_ok=True)


def test_product_image_upload_requires_admin_and_valid_image(client: TestClient):
    customer_token = register(client)
    endpoint = "/api/admin/uploads/images"
    denied = client.post(
        endpoint,
        headers={"Authorization": f"Bearer {customer_token}", "Content-Type": "image/png"},
        content=b"\x89PNG\r\n\x1a\n",
    )
    assert denied.status_code == 403

    admin = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "test-admin-password"}
    )
    invalid = client.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {admin.json()['access_token']}",
            "Content-Type": "image/png",
        },
        content=b"not an image",
    )
    assert invalid.status_code == 415


def test_google_oauth_config_requires_complete_credentials(client: TestClient, monkeypatch):
    monkeypatch.setattr(backend_main.settings, "google_oauth_client_id", "client-id")
    monkeypatch.setattr(backend_main.settings, "google_oauth_client_secret", None)
    monkeypatch.setattr(
        backend_main.settings, "google_oauth_redirect_uri", "http://localhost:5173/oauth/callback"
    )
    response = client.get("/api/auth/google/config")
    assert response.status_code == 503


def test_google_oauth_config_returns_client_settings(client: TestClient, monkeypatch):
    monkeypatch.setattr(backend_main.settings, "google_oauth_client_id", "client-id")
    monkeypatch.setattr(backend_main.settings, "google_oauth_client_secret", "client-secret")
    monkeypatch.setattr(
        backend_main.settings,
        "google_oauth_redirect_uri",
        "http://localhost:5173/oauth/callback",
    )
    response = client.get("/api/auth/google/config")
    assert response.status_code == 200
    assert response.json() == {
        "client_id": "client-id",
        "redirect_uri": "http://localhost:5173/oauth/callback",
    }


def test_google_identity_accepts_small_clock_skew(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(datetime.now(UTC).timestamp())
    nonce = "n" * 32
    identity_token = backend_main.jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "aud": "client-id",
            "sub": "google-user-456",
            "email": "google-buyer@example.com",
            "email_verified": True,
            "iat": now + 30,
            "exp": now + 300,
            "nonce": nonce,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    monkeypatch.setattr(backend_main.settings, "google_oauth_client_id", "client-id")
    monkeypatch.setattr(backend_main.settings, "google_oauth_client_secret", "client-secret")
    monkeypatch.setattr(
        backend_main.settings,
        "google_oauth_redirect_uri",
        "http://localhost:5173/oauth/callback",
    )
    monkeypatch.setattr(
        backend_main,
        "GOOGLE_JWKS_CLIENT",
        SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private_key.public_key())
        ),
    )

    class TokenResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return json.dumps({"id_token": identity_token}).encode()

    monkeypatch.setattr(backend_main, "urlopen", lambda *_args, **_kwargs: TokenResponse())
    claims = backend_main.google_identity_from_code(
        GoogleCodeExchange(code="authorization-code", code_verifier="v" * 43, nonce=nonce)
    )
    assert claims["sub"] == "google-user-456"


def test_google_oauth_exchange_creates_user_and_allows_order_history(
    client: TestClient, monkeypatch
):
    monkeypatch.setattr(
        backend_main,
        "google_identity_from_code",
        lambda payload: {
            "sub": "google-user-123",
            "email": "google-buyer@example.com",
            "email_verified": True,
        },
    )
    response = client.post(
        "/api/auth/google/exchange",
        json={"code": "authorization-code", "code_verifier": "v" * 43, "nonce": "n" * 32},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    user = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert user.status_code == 200
    assert user.json()["email"] == "google-buyer@example.com"
    assert client.get("/api/orders", headers={"Authorization": f"Bearer {token}"}).json() == []

    repeated = client.post(
        "/api/auth/google/exchange",
        json={"code": "another-code", "code_verifier": "v" * 43, "nonce": "n" * 32},
    )
    assert repeated.status_code == 200
    assert (
        client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {repeated.json()['access_token']}"},
        ).json()["id"]
        == user.json()["id"]
    )


def test_google_oauth_links_existing_email_without_disabling_password_login(
    client: TestClient, monkeypatch
):
    monkeypatch.setattr(
        backend_main,
        "google_identity_from_code",
        lambda payload: {
            "sub": "google-admin-123",
            "email": "admin@example.com",
            "email_verified": True,
        },
    )
    response = client.post(
        "/api/auth/google/exchange",
        json={"code": "authorization-code", "code_verifier": "v" * 43, "nonce": "n" * 32},
    )
    assert response.status_code == 200
    user = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert user.status_code == 200
    assert user.json()["role"] == "admin"

    password_login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "test-admin-password"},
    )
    assert password_login.status_code == 200
