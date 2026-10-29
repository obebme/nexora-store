import hashlib
import hmac
import json
import logging
import secrets
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request as URLRequest
from urllib.request import urlopen
from uuid import uuid4

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import String, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from .config import settings
from .database import get_db
from .email_service import (
    EmailDeliveryError,
    send_email_verified_notice,
    send_password_reset_email,
    send_verification_email,
)
from .models import Cart, CartItem, Category, Order, OrderItem, Product, User
from .payment_service import YooKassaError
from .payment_service import cancel_payment as cancel_yookassa_payment
from .payment_service import create_payment as create_yookassa_payment
from .payment_service import create_refund as create_yookassa_refund
from .payment_service import get_payment as get_yookassa_payment
from .payment_service import get_refund as get_yookassa_refund
from .schemas import (
    CartItemCreate,
    CartItemOut,
    CartOut,
    CartReplace,
    CategoryOut,
    EmailActionOut,
    EmailOnly,
    EmailVerificationOut,
    GoogleCodeExchange,
    GoogleOAuthConfigOut,
    OrderCreate,
    OrderOut,
    OrderStatusUpdate,
    PasswordResetConfirm,
    PaymentConfirmationOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    TokenOut,
    UserCreate,
    UserOut,
    YooKassaWebhook,
)
from .security import admin_user, create_access_token, current_user, hash_password, verify_password

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(admin_user)]

UPLOADS_DIR = (settings.uploads_dir or Path(__file__).resolve().parents[2] / "uploads").resolve()
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
GOOGLE_JWKS_CLIENT = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs")
MAX_IMAGE_SIZE = 5 * 1024 * 1024
IMAGE_FORMATS = {
    "image/jpeg": (".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
    "image/png": (".png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/gif": (".gif", lambda data: data.startswith((b"GIF87a", b"GIF89a"))),
    "image/webp": (".webp", lambda data: data.startswith(b"RIFF") and data[8:12] == b"WEBP"),
}

app = FastAPI(title=settings.app_name, version="0.1.0")
logger = logging.getLogger(__name__)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: DbSession) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"database": "ok"}


@app.get("/api/payments/config")
def payment_config() -> dict[str, bool]:
    configured = bool(settings.yookassa_shop_id and settings.yookassa_secret_key)
    return {
        "configured": configured,
        "sales_enabled": settings.sales_enabled,
        "checkout_available": configured and settings.sales_enabled,
    }


@app.get("/api/categories", response_model=list[CategoryOut])
def list_categories(db: DbSession) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.name)))


@app.get("/api/products", response_model=list[ProductOut])
def list_products(
    db: DbSession,
    category: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    sort: str = Query(default="featured", pattern="^(featured|price_asc|price_desc)$"),
    limit: int = Query(default=60, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Product]:
    statement = (
        select(Product).options(joinedload(Product.category)).where(Product.is_active.is_(True))
    )
    if category:
        statement = statement.join(Product.category).where(Category.slug == category)
    if q:
        statement = statement.where(Product.name.ilike(f"%{q}%"))
    if sort == "price_asc":
        statement = statement.order_by(Product.price.asc(), Product.id.asc())
    elif sort == "price_desc":
        statement = statement.order_by(Product.price.desc(), Product.id.asc())
    else:
        statement = statement.order_by(Product.created_at.desc(), Product.id.asc())
    return list(db.scalars(statement.offset(offset).limit(limit)).unique())


def get_or_create_cart(db: Session, user: User) -> Cart:
    cart = db.scalar(
        select(Cart)
        .options(selectinload(Cart.items).joinedload(CartItem.product))
        .where(Cart.user_id == user.id)
    )
    if cart is None:
        cart = Cart(user_id=user.id)
        db.add(cart)
        db.flush()
    return cart


def cart_response(cart: Cart) -> CartOut:
    items = [
        CartItemOut(
            product_id=line.product_id,
            name=line.product.name,
            slug=line.product.slug,
            sku=line.product.sku,
            selected_size=line.selected_size,
            quantity=line.quantity,
            size_stock_quantity=size_stock(line.product, line.selected_size),
            unit_price=line.product.price,
            image_url=line.product.image_url,
            line_total=line.product.price * line.quantity,
        )
        for line in cart.items
    ]
    return CartOut(
        items=items,
        item_count=sum(line.quantity for line in cart.items),
        total_amount=sum((line.line_total for line in items), Decimal("0.00")),
    )


def distributed_stock(total: int, sizes: list[str]) -> dict[str, int]:
    size_names = list(dict.fromkeys(sizes or ["ONE SIZE"]))
    quotient, remainder = divmod(total, len(size_names))
    return {
        size: quotient + (1 if index < remainder else 0) for index, size in enumerate(size_names)
    }


def product_stock_by_size(product: Product) -> dict[str, int]:
    return product.effective_stock_by_size.copy()


def size_stock(product: Product, size: str) -> int:
    return product_stock_by_size(product).get(size, 0)


def create_verification_request(user: User, db: Session) -> str:
    token = secrets.token_urlsafe(32)
    user.verification_token_hash = hashlib.sha256(token.encode()).hexdigest()
    user.verification_expires_at = datetime.now(UTC) + timedelta(hours=24)
    db.commit()
    return token


def send_verification_or_error(email: str, token: str) -> None:
    try:
        send_verification_email(email, token)
    except EmailDeliveryError as error:
        logger.warning("Verification email delivery failed: %s", str(error))
        raise HTTPException(
            status_code=503,
            detail=(
                "Аккаунт создан, но письмо не отправлено. Проверь настройки почты "
                "или запроси письмо повторно."
            ),
        ) from None


@app.post(
    "/api/auth/register",
    response_model=EmailActionOut,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: UserCreate, db: DbSession) -> EmailActionOut:
    email = str(payload.email).lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="Этот email уже зарегистрирован")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        email_verified=False,
    )
    db.add(user)
    try:
        db.flush()
        user.cart = Cart()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Этот email уже зарегистрирован") from None
    db.refresh(user)
    token = create_verification_request(user, db)
    send_verification_or_error(email, token)
    return EmailActionOut(message="Письмо отправлено. Подтверди email по ссылке из письма.")


@app.post("/api/auth/resend-verification", response_model=EmailActionOut)
def resend_verification(payload: EmailOnly, db: DbSession) -> EmailActionOut:
    email = str(payload.email).lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and not user.email_verified:
        token = create_verification_request(user, db)
        send_verification_or_error(email, token)
    return EmailActionOut(
        message="Если для этого адреса есть неподтверждённый аккаунт, письмо отправлено."
    )


@app.get("/api/auth/verify-email", response_model=EmailVerificationOut)
def verify_email(
    db: DbSession, token: str = Query(min_length=32, max_length=128)
) -> EmailVerificationOut:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user = db.scalar(select(User).where(User.verification_token_hash == token_hash))
    if user is None:
        raise HTTPException(status_code=400, detail="Ссылка недействительна или уже использована")
    expires_at = user.verification_expires_at
    if expires_at is None:
        raise HTTPException(status_code=400, detail="Ссылка подтверждения недействительна")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        user.verification_token_hash = None
        user.verification_expires_at = None
        db.commit()
        raise HTTPException(
            status_code=400, detail="Срок действия ссылки истёк. Запроси письмо повторно."
        )

    user.email_verified = True
    user.verification_token_hash = None
    user.verification_expires_at = None
    db.commit()
    try:
        send_email_verified_notice(user.email)
    except EmailDeliveryError as error:
        logger.warning("Email confirmation notice delivery failed: %s", str(error))
        return EmailVerificationOut(
            email=user.email,
            verified=True,
            notification_sent=False,
            message="Почта подтверждена, но письмо с подтверждением отправить не удалось.",
        )
    return EmailVerificationOut(
        email=user.email,
        verified=True,
        notification_sent=True,
        message="Почта подтверждена. Мы отправили уведомление на ваш email.",
    )


@app.post("/api/auth/password-reset/request", response_model=EmailActionOut)
def request_password_reset(payload: EmailOnly, db: DbSession) -> EmailActionOut:
    email = str(payload.email).lower()
    user = db.scalar(
        select(User).where(
            User.email == email, User.email_verified.is_(True), User.is_active.is_(True)
        )
    )
    if user is not None:
        token = secrets.token_urlsafe(32)
        user.password_reset_token_hash = hashlib.sha256(token.encode()).hexdigest()
        user.password_reset_expires_at = datetime.now(UTC) + timedelta(hours=1)
        db.commit()
        try:
            send_password_reset_email(email, token)
        except EmailDeliveryError as error:
            logger.warning("Password reset email delivery failed: %s", str(error))
            raise HTTPException(
                status_code=503, detail="Не удалось отправить письмо. Попробуй позже."
            ) from None
    return EmailActionOut(
        message="Если аккаунт с таким подтверждённым email существует, письмо для сброса пароля отправлено."
    )


@app.post("/api/auth/password-reset/confirm", response_model=EmailActionOut)
def confirm_password_reset(payload: PasswordResetConfirm, db: DbSession) -> EmailActionOut:
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    user = db.scalar(select(User).where(User.password_reset_token_hash == token_hash))
    if user is None:
        raise HTTPException(
            status_code=400, detail="Ссылка сброса пароля недействительна или уже использована"
        )
    expires_at = user.password_reset_expires_at
    if expires_at is None:
        raise HTTPException(status_code=400, detail="Ссылка сброса пароля недействительна")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        db.commit()
        raise HTTPException(
            status_code=400, detail="Срок действия ссылки истёк. Запроси сброс повторно."
        )

    user.password_hash = hash_password(payload.new_password)
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    db.commit()
    return EmailActionOut(message="Пароль обновлён. Теперь можно войти в аккаунт.")


def google_identity_from_code(payload: GoogleCodeExchange) -> dict[str, object]:
    if not (
        settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and settings.google_oauth_redirect_uri
    ):
        raise HTTPException(status_code=503, detail="Вход через Google пока не настроен")
    redirect = urlsplit(settings.google_oauth_redirect_uri)
    if redirect.scheme != "https" and redirect.hostname not in {"localhost", "127.0.0.1"}:
        raise HTTPException(status_code=503, detail="Некорректный Google OAuth redirect URI")

    token_request = URLRequest(
        "https://oauth2.googleapis.com/token",
        data=urlencode(
            {
                "code": payload.code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": payload.code_verifier,
            }
        ).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(token_request, timeout=10) as response:
            token_response = json.loads(response.read())
    except HTTPError:
        raise HTTPException(
            status_code=401, detail="Google не подтвердил код авторизации"
        ) from None
    except URLError, TimeoutError:
        raise HTTPException(status_code=502, detail="Сервис Google временно недоступен") from None
    except json.JSONDecodeError, UnicodeDecodeError:
        raise HTTPException(status_code=502, detail="Google вернул некорректный ответ") from None

    id_token = token_response.get("id_token") if isinstance(token_response, dict) else None
    if not isinstance(id_token, str):
        raise HTTPException(
            status_code=401, detail="В ответе Google отсутствует токен пользователя"
        )
    try:
        signing_key = GOOGLE_JWKS_CLIENT.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.google_oauth_client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
            leeway=60,
            options={"require": ["sub", "exp", "iat", "nonce", "email", "email_verified"]},
        )
    except jwt.PyJWTError as error:
        logger.warning("Google ID token verification failed: %s", type(error).__name__)
        raise HTTPException(
            status_code=401, detail="Не удалось проверить учетную запись Google"
        ) from None

    if (
        not isinstance(claims.get("sub"), str)
        or not isinstance(claims.get("email"), str)
        or claims.get("email_verified") is not True
        or not isinstance(claims.get("nonce"), str)
        or not hmac.compare_digest(claims["nonce"], payload.nonce)
    ):
        raise HTTPException(status_code=401, detail="Google не подтвердил email или nonce")
    return claims


@app.get("/api/auth/google/config", response_model=GoogleOAuthConfigOut)
def google_oauth_config() -> GoogleOAuthConfigOut:
    if not (
        settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and settings.google_oauth_redirect_uri
    ):
        raise HTTPException(status_code=503, detail="Вход через Google пока не настроен")
    return GoogleOAuthConfigOut(
        client_id=settings.google_oauth_client_id,
        redirect_uri=settings.google_oauth_redirect_uri,
    )


@app.post("/api/auth/google/exchange", response_model=TokenOut)
def google_oauth_exchange(payload: GoogleCodeExchange, db: DbSession) -> TokenOut:
    identity = google_identity_from_code(payload)
    email = str(identity["email"]).lower()
    google_sub = str(identity["sub"])
    user = db.scalar(select(User).where(User.google_sub == google_sub))
    email_user = db.scalar(select(User).where(User.email == email))

    if user is not None and email_user is not None and email_user.id != user.id:
        raise HTTPException(
            status_code=409, detail="Этот Google email уже связан с другим аккаунтом"
        )
    if user is None:
        if email_user is not None:
            if email_user.google_sub not in {None, google_sub}:
                raise HTTPException(
                    status_code=409, detail="Этот email уже связан с другим Google аккаунтом"
                )
            user = email_user
            user.google_sub = google_sub
        else:
            user = User(
                email=email,
                google_sub=google_sub,
                password_hash=hash_password(secrets.token_urlsafe(48)),
            )
            db.add(user)
            db.flush()
            user.cart = Cart()
    elif user.email != email:
        user.email = email

    if user.cart is None:
        db.add(Cart(user_id=user.id))
    user.is_active = True
    user.email_verified = True
    user.verification_token_hash = None
    user.verification_expires_at = None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Не удалось связать Google аккаунт") from None
    db.refresh(user)
    return TokenOut(access_token=create_access_token(user))


@app.post("/api/auth/login", response_model=TokenOut)
def login(payload: UserCreate, db: DbSession) -> TokenOut:
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=401,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Сначала подтверди email по ссылке из письма.",
        )
    return TokenOut(access_token=create_access_token(user))


@app.get("/api/auth/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@app.get("/api/cart", response_model=CartOut)
def get_cart(user: CurrentUser, db: DbSession) -> CartOut:
    return cart_response(get_or_create_cart(db, user))


@app.put("/api/cart", response_model=CartOut)
def replace_cart(payload: CartReplace, user: CurrentUser, db: DbSession) -> CartOut:
    cart = get_or_create_cart(db, user)
    desired: dict[tuple[int, str], int] = {}
    for item in payload.items:
        key = (item.product_id, item.selected_size)
        desired[key] = desired.get(key, 0) + item.quantity
    products = {
        product.id: product
        for product in db.scalars(
            select(Product).where(Product.id.in_({product_id for product_id, _ in desired}))
        )
    }
    if any(line.product_id not in products for line in cart.items):
        raise HTTPException(status_code=409, detail="Один из товаров больше недоступен")
    for (product_id, selected_size), quantity in desired.items():
        product = products.get(product_id)
        if product is None or not product.is_active:
            raise HTTPException(status_code=409, detail="Один из товаров больше недоступен")
        if selected_size not in (product.sizes or ["ONE SIZE"]):
            raise HTTPException(status_code=409, detail=f"Размер {selected_size} больше недоступен")
        if quantity > size_stock(product, selected_size):
            raise HTTPException(
                status_code=409,
                detail=f"Для товара «{product.name}», размер {selected_size}, недостаточно остатка",
            )
    cart.items.clear()
    for (product_id, selected_size), quantity in desired.items():
        cart.items.append(
            CartItem(
                product=products[product_id],
                selected_size=selected_size,
                quantity=quantity,
            )
        )
    db.commit()
    return cart_response(get_or_create_cart(db, user))


@app.post("/api/cart/items", response_model=CartOut, status_code=status.HTTP_200_OK)
def add_cart_item(payload: CartItemCreate, user: CurrentUser, db: DbSession) -> CartOut:
    product = db.scalar(
        select(Product).where(Product.id == payload.product_id, Product.is_active.is_(True))
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    if payload.selected_size not in (product.sizes or ["ONE SIZE"]):
        raise HTTPException(status_code=422, detail="Такого размера нет в наличии")
    cart = get_or_create_cart(db, user)
    line = next(
        (
            line
            for line in cart.items
            if line.product_id == product.id and line.selected_size == payload.selected_size
        ),
        None,
    )
    current_quantity = sum(
        cart_line.quantity
        for cart_line in cart.items
        if cart_line.product_id == product.id and cart_line.selected_size == payload.selected_size
    )
    if current_quantity + payload.quantity > size_stock(product, payload.selected_size):
        raise HTTPException(status_code=409, detail="Недостаточно товара на складе")
    if line:
        line.quantity += payload.quantity
    else:
        cart.items.append(
            CartItem(
                product=product, selected_size=payload.selected_size, quantity=payload.quantity
            )
        )
    db.commit()
    return cart_response(get_or_create_cart(db, user))


@app.patch("/api/cart/items/{product_id}/{selected_size}", response_model=CartOut)
def set_cart_quantity(
    product_id: int,
    selected_size: str,
    user: CurrentUser,
    db: DbSession,
    quantity: int = Query(ge=0, le=20),
) -> CartOut:
    cart = get_or_create_cart(db, user)
    line = next(
        (
            line
            for line in cart.items
            if line.product_id == product_id and line.selected_size == selected_size
        ),
        None,
    )
    if line is None:
        raise HTTPException(status_code=404, detail="Позиция в корзине не найдена")
    if quantity == 0:
        db.delete(line)
    else:
        if quantity > size_stock(line.product, selected_size):
            raise HTTPException(status_code=409, detail="Недостаточно товара на складе")
        line.quantity = quantity
    db.commit()
    return cart_response(get_or_create_cart(db, user))


@app.delete("/api/cart/items/{product_id}/{selected_size}", response_model=CartOut)
def delete_cart_item(
    product_id: int, selected_size: str, user: CurrentUser, db: DbSession
) -> CartOut:
    cart = get_or_create_cart(db, user)
    line = next(
        (
            line
            for line in cart.items
            if line.product_id == product_id and line.selected_size == selected_size
        ),
        None,
    )
    if line is not None:
        db.delete(line)
        db.commit()
    return cart_response(get_or_create_cart(db, user))


@app.post("/api/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreate, user: CurrentUser, db: DbSession) -> Order:
    if not settings.sales_enabled:
        raise HTTPException(
            status_code=503,
            detail="Приём заказов отключён до подключения и проверки доставки СДЭК",
        )
    cart = get_or_create_cart(db, user)
    if not cart.items:
        raise HTTPException(status_code=400, detail="Корзина пуста")
    products = {
        product.id: product
        for product in db.scalars(
            select(Product)
            .where(Product.id.in_({line.product_id for line in cart.items}))
            .order_by(Product.id)
            .with_for_update()
        )
    }
    if any(products[line.product_id].currency_code != "RUB" for line in cart.items):
        raise HTTPException(
            status_code=409,
            detail="В заказ можно добавить только товары с ценой в рублях",
        )
    total = sum(
        (products[line.product_id].price * line.quantity for line in cart.items),
        Decimal("0.00"),
    )
    if total <= 0:
        raise HTTPException(status_code=409, detail="Сумма заказа должна быть больше нуля")
    order = Order(
        user_id=user.id,
        status="pending",
        payment_status="pending",
        payment_idempotence_key=str(uuid4()),
        reservation_expires_at=datetime.now(UTC)
        + timedelta(minutes=settings.order_reservation_minutes),
        total_amount=total,
        currency_code="RUB",
        shipping_name=payload.shipping.name,
        shipping_address_line1=payload.shipping.address_line1,
        shipping_address_line2=payload.shipping.address_line2,
        shipping_city=payload.shipping.city,
        shipping_region=payload.shipping.region,
        shipping_postal_code=payload.shipping.postal_code,
        shipping_country_code=payload.shipping.country_code.upper(),
        shipping_phone=payload.shipping.phone,
    )
    for line in cart.items:
        product = products.get(line.product_id)
        if (
            product is None
            or size_stock(product, line.selected_size) < line.quantity
            or not product.is_active
        ):
            raise HTTPException(
                status_code=409, detail=f"Недостаточно товара «{line.product.name}»"
            )
        inventory = product_stock_by_size(product)
        inventory[line.selected_size] -= line.quantity
        product.stock_by_size = inventory
        product.stock_quantity -= line.quantity
        order.items.append(
            OrderItem(
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                selected_size=line.selected_size,
                unit_price=product.price,
                quantity=line.quantity,
            )
        )
    db.add(order)
    cart.items.clear()
    db.commit()
    db.refresh(order)
    return order


def sync_yookassa_payment(db: Session, order: Order, payment: dict) -> None:
    if payment.get("id") != order.yookassa_payment_id:
        raise HTTPException(status_code=400, detail="Платёж не соответствует заказу")
    metadata = payment.get("metadata")
    amount = payment.get("amount")
    if (
        not isinstance(metadata, dict)
        or metadata.get("order_id") != str(order.id)
        or not isinstance(amount, dict)
        or amount.get("currency") != order.currency_code
    ):
        raise HTTPException(status_code=400, detail="Параметры платежа не соответствуют заказу")
    try:
        paid_amount = Decimal(str(amount["value"]))
    except KeyError, ArithmeticError, ValueError:
        raise HTTPException(
            status_code=400, detail="ЮKassa вернула некорректную сумму платежа"
        ) from None
    if paid_amount != order.total_amount:
        raise HTTPException(status_code=400, detail="Сумма платежа не соответствует заказу")

    payment_status = payment.get("status")
    if payment_status == "succeeded":
        order.payment_status = "paid"
        if order.status == "pending":
            order.status = "processing"
    elif payment_status == "canceled":
        order.payment_status = "failed"
    else:
        return
    db.commit()


@app.post(
    "/api/orders/{order_id}/payment",
    response_model=PaymentConfirmationOut,
)
def create_order_payment(order_id: int, user: CurrentUser, db: DbSession) -> PaymentConfirmationOut:
    order = db.scalar(
        select(Order).where(Order.id == order_id, Order.user_id == user.id).with_for_update()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if not settings.sales_enabled:
        raise HTTPException(status_code=503, detail="Приём заказов временно отключён")
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        raise HTTPException(status_code=503, detail="Оплата ЮKassa не настроена")
    if order.status == "cancelled":
        raise HTTPException(status_code=409, detail="Заказ отменён")
    if order.status != "pending":
        raise HTTPException(status_code=409, detail="Заказ уже передан в обработку")
    expiration = order.reservation_expires_at or (
        order.created_at + timedelta(minutes=settings.order_reservation_minutes)
    )
    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=UTC)
    if expiration <= datetime.now(UTC):
        raise HTTPException(
            status_code=409,
            detail="Время оплаты истекло. Заказ будет отменён, а товар возвращён в остаток.",
        )
    if order.payment_status == "paid":
        raise HTTPException(status_code=409, detail="Заказ уже оплачен")
    if order.payment_status not in {"pending", "failed"}:
        raise HTTPException(status_code=409, detail="Для заказа недоступна повторная оплата")
    if order.yookassa_payment_id:
        try:
            payment = get_yookassa_payment(order.yookassa_payment_id)
        except YooKassaError as error:
            logger.warning("YooKassa payment lookup failed: %s", str(error))
            raise HTTPException(
                status_code=502, detail="Не удалось проверить платёж в ЮKassa"
            ) from None
        sync_yookassa_payment(db, order, payment)
        if order.payment_status == "paid":
            raise HTTPException(status_code=409, detail="Заказ уже оплачен")
        if order.payment_status == "pending" and order.payment_confirmation_url:
            return PaymentConfirmationOut(confirmation_url=order.payment_confirmation_url)

    if order.payment_status == "failed":
        order.yookassa_payment_id = None
        order.payment_confirmation_url = None
        order.payment_status = "pending"
        order.payment_idempotence_key = str(uuid4())
        db.commit()
    elif order.payment_idempotence_key is None:
        order.payment_idempotence_key = str(uuid4())
        db.commit()
    idempotence_key = order.payment_idempotence_key
    if idempotence_key is None:
        raise HTTPException(
            status_code=500, detail="Не удалось подготовить безопасную попытку оплаты"
        )
    try:
        payment = create_yookassa_payment(
            order_id=order.id,
            amount=order.total_amount,
            currency=order.currency_code,
            description=f"NEXORA — заказ №{order.id}",
            idempotence_key=idempotence_key,
        )
    except YooKassaError as error:
        logger.warning("YooKassa payment creation failed for order %s: %s", order.id, str(error))
        raise HTTPException(status_code=502, detail="Не удалось создать платёж в ЮKassa") from None

    confirmation = payment.get("confirmation")
    confirmation_url = (
        confirmation.get("confirmation_url") if isinstance(confirmation, dict) else None
    )
    payment_id = payment.get("id")
    if (
        not isinstance(payment_id, str)
        or not isinstance(confirmation_url, str)
        or urlsplit(confirmation_url).scheme != "https"
        or not urlsplit(confirmation_url).netloc
    ):
        raise HTTPException(status_code=502, detail="ЮKassa вернула некорректные данные платежа")
    order.yookassa_payment_id = payment_id
    order.payment_confirmation_url = confirmation_url
    db.commit()
    return PaymentConfirmationOut(confirmation_url=confirmation_url)


@app.post("/api/payments/yookassa/webhook")
def yookassa_webhook(payload: YooKassaWebhook, db: DbSession) -> dict[str, str]:
    if payload.event.startswith("refund."):
        try:
            refund = get_yookassa_refund(payload.object.id)
        except YooKassaError as error:
            logger.warning("YooKassa refund webhook verification failed: %s", str(error))
            raise HTTPException(
                status_code=502, detail="Не удалось проверить возврат ЮKassa"
            ) from None
        expected_status = "succeeded" if payload.event == "refund.succeeded" else "canceled"
        if refund.get("status") != expected_status:
            raise HTTPException(
                status_code=400, detail="Статус возврата не соответствует уведомлению"
            )
        order = db.scalar(
            select(Order).where(Order.yookassa_refund_id == payload.object.id).with_for_update()
        )
        if order is None:
            raise HTTPException(status_code=503, detail="Возврат ещё не связан с заказом")
        sync_yookassa_refund(db, order, refund)
        return {"status": "ok"}

    try:
        payment = get_yookassa_payment(payload.object.id)
    except YooKassaError as error:
        logger.warning("YooKassa webhook verification failed: %s", str(error))
        raise HTTPException(
            status_code=502, detail="Не удалось проверить уведомление ЮKassa"
        ) from None
    expected_status = "succeeded" if payload.event == "payment.succeeded" else "canceled"
    if payment.get("status") != expected_status:
        raise HTTPException(status_code=400, detail="Статус платежа не соответствует уведомлению")
    order = db.scalar(
        select(Order).where(Order.yookassa_payment_id == payload.object.id).with_for_update()
    )
    if order is None:
        raise HTTPException(
            status_code=503,
            detail="Платёж ещё не связан с заказом; ЮKassa может повторить уведомление",
        )
    sync_yookassa_payment(db, order, payment)
    return {"status": "ok"}


def sync_yookassa_refund(db: Session, order: Order, refund: dict) -> None:
    amount = refund.get("amount")
    if (
        refund.get("id") != order.yookassa_refund_id
        or refund.get("payment_id") != order.yookassa_payment_id
        or not isinstance(amount, dict)
        or amount.get("currency") != order.currency_code
    ):
        raise HTTPException(status_code=400, detail="Возврат не соответствует заказу")
    try:
        refund_amount = Decimal(str(amount["value"]))
    except KeyError, ArithmeticError, ValueError:
        raise HTTPException(
            status_code=400, detail="ЮKassa вернула некорректную сумму возврата"
        ) from None
    if refund_amount != order.total_amount:
        raise HTTPException(status_code=400, detail="Сумма возврата не соответствует заказу")
    refund_status = refund.get("status")
    if refund_status not in {"pending", "succeeded", "canceled"}:
        raise HTTPException(status_code=400, detail="ЮKassa вернула неизвестный статус возврата")
    order.refund_status = refund_status
    if refund_status == "succeeded":
        order.payment_status = "refunded"
    db.commit()


def restore_order_inventory(db: Session, order: Order) -> None:
    for item in order.items:
        if item.product_id is None:
            continue
        product = db.scalar(select(Product).where(Product.id == item.product_id).with_for_update())
        if product is None:
            continue
        inventory = product_stock_by_size(product)
        size = item.selected_size or "ONE SIZE"
        inventory[size] = inventory.get(size, 0) + item.quantity
        product.stock_by_size = inventory
        product.stock_quantity += item.quantity


def expire_unpaid_orders(db: Session, now: datetime | None = None) -> int:
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    cutoff = current_time - timedelta(minutes=settings.order_reservation_minutes)
    expiry_filter = or_(
        Order.reservation_expires_at <= current_time,
        (Order.reservation_expires_at.is_(None) & (Order.created_at <= cutoff)),
    )
    expired_order_ids = db.scalars(
        select(Order.id)
        .where(
            Order.status == "pending",
            Order.payment_status.in_(("pending", "failed")),
            expiry_filter,
        )
        .order_by(Order.id)
    ).all()
    expired_count = 0
    for order_id in expired_order_ids:
        order = db.scalar(
            select(Order)
            .options(selectinload(Order.items))
            .where(
                Order.id == order_id,
                Order.status == "pending",
                Order.payment_status.in_(("pending", "failed")),
                expiry_filter,
            )
            .with_for_update(skip_locked=True)
        )
        if order is None:
            continue
        if order.payment_status == "pending" and order.yookassa_payment_id:
            try:
                payment = get_yookassa_payment(order.yookassa_payment_id)
            except YooKassaError as error:
                logger.warning(
                    "Could not verify expired order %s payment: %s", order.id, str(error)
                )
                continue
            try:
                sync_yookassa_payment(db, order, payment)
            except HTTPException as error:
                logger.error(
                    "Expired order %s payment verification failed: %s", order.id, error.detail
                )
                db.rollback()
                continue
            if order.payment_status == "paid":
                continue
            if payment.get("status") == "pending":
                if order.payment_cancel_idempotence_key is None:
                    order.payment_cancel_idempotence_key = str(uuid4())
                    db.commit()
                try:
                    payment = cancel_yookassa_payment(
                        order.yookassa_payment_id,
                        order.payment_cancel_idempotence_key,
                    )
                except YooKassaError as error:
                    logger.warning(
                        "Could not cancel expired order %s payment: %s", order.id, str(error)
                    )
                    continue
                try:
                    sync_yookassa_payment(db, order, payment)
                except HTTPException as error:
                    logger.error(
                        "Expired order %s cancellation verification failed: %s",
                        order.id,
                        error.detail,
                    )
                    db.rollback()
                    continue
        if order.payment_status == "paid":
            continue
        if order.payment_status == "pending" and order.yookassa_payment_id:
            continue
        if order.payment_status not in {"pending", "failed"}:
            continue
        restore_order_inventory(db, order)
        order.status = "cancelled"
        order.payment_status = "failed"
        db.commit()
        expired_count += 1
    return expired_count


@app.post("/api/admin/orders/{order_id}/refund", response_model=OrderOut)
def refund_order(order_id: int, _: AdminUser, db: DbSession) -> Order:
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
        .with_for_update()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        raise HTTPException(status_code=503, detail="Оплата ЮKassa не настроена")
    if order.payment_status == "refunded":
        return order
    if order.payment_status != "paid" or not order.yookassa_payment_id:
        raise HTTPException(status_code=409, detail="Можно вернуть только оплаченный заказ")

    if order.yookassa_refund_id:
        try:
            refund = get_yookassa_refund(order.yookassa_refund_id)
        except YooKassaError as error:
            logger.warning("YooKassa refund lookup failed for order %s: %s", order.id, str(error))
            raise HTTPException(
                status_code=502, detail="Не удалось проверить возврат в ЮKassa"
            ) from None
        sync_yookassa_refund(db, order, refund)
        if order.refund_status != "canceled":
            return order
        order.yookassa_refund_id = None
        order.refund_idempotence_key = None

    if order.refund_idempotence_key is None:
        order.refund_idempotence_key = str(uuid4())
        db.commit()
    try:
        refund = create_yookassa_refund(
            payment_id=order.yookassa_payment_id,
            amount=order.total_amount,
            currency=order.currency_code,
            description=f"NEXORA — возврат по заказу №{order.id}",
            idempotence_key=order.refund_idempotence_key,
        )
    except YooKassaError as error:
        logger.warning("YooKassa refund creation failed for order %s: %s", order.id, str(error))
        raise HTTPException(status_code=502, detail="Не удалось создать возврат в ЮKassa") from None
    refund_id = refund.get("id")
    if not isinstance(refund_id, str):
        raise HTTPException(status_code=502, detail="ЮKassa вернула некорректные данные возврата")
    order.yookassa_refund_id = refund_id
    db.commit()
    sync_yookassa_refund(db, order, refund)
    return order


@app.get("/api/orders", response_model=list[OrderOut])
def my_orders(user: CurrentUser, db: DbSession) -> list[Order]:
    return list(
        db.scalars(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.user_id == user.id)
            .order_by(Order.created_at.desc())
        )
    )


@app.get("/api/admin/orders", response_model=list[OrderOut])
def admin_orders(
    _: AdminUser,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, min_length=1, max_length=160),
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[Order]:
    statement = (
        select(Order)
        .join(User, Order.user_id == User.id)
        .options(selectinload(Order.items), joinedload(Order.user))
    )
    if status_filter:
        statement = statement.where(Order.status == status_filter)
    if q:
        search = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                User.email.ilike(search),
                Order.shipping_name.ilike(search),
                Order.shipping_address_line1.ilike(search),
                Order.shipping_city.ilike(search),
                Order.shipping_postal_code.ilike(search),
                Order.id.cast(String).ilike(search),
            )
        )
    if date_from:
        statement = statement.where(Order.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        statement = statement.where(
            Order.created_at < datetime.combine(date_to + timedelta(days=1), time.min)
        )
    return list(db.scalars(statement.order_by(Order.created_at.desc())))


@app.get("/api/admin/products", response_model=list[ProductOut])
def admin_products(_: AdminUser, db: DbSession) -> list[Product]:
    return list(
        db.scalars(
            select(Product)
            .options(joinedload(Product.category))
            .order_by(Product.created_at.desc())
        ).unique()
    )


@app.post("/api/admin/uploads/images")
async def upload_product_image(request: Request, _: AdminUser) -> dict[str, str]:
    content_type = request.headers.get("content-type", "").split(";", maxsplit=1)[0].strip().lower()
    image_format = IMAGE_FORMATS.get(content_type)
    if image_format is None:
        raise HTTPException(status_code=415, detail="Поддерживаются JPEG, PNG, GIF и WebP.")

    content_length = request.headers.get("content-length")
    if content_length is not None:
        if not content_length.isdecimal():
            raise HTTPException(status_code=400, detail="Некорректный размер загружаемого файла.")
        if int(content_length) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=413, detail="Размер изображения не должен превышать 5 МБ."
            )

    image_data = bytearray()
    async for chunk in request.stream():
        if len(image_data) + len(chunk) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=413, detail="Размер изображения не должен превышать 5 МБ."
            )
        image_data.extend(chunk)

    extension, matches_format = image_format
    if not matches_format(image_data):
        raise HTTPException(status_code=415, detail="Формат файла не соответствует изображению.")

    filename = f"{uuid4().hex}{extension}"
    (UPLOADS_DIR / filename).write_bytes(image_data)
    return {"image_url": f"/uploads/{filename}"}


@app.patch("/api/admin/orders/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: int, payload: OrderStatusUpdate, _: AdminUser, db: DbSession
) -> Order:
    order = db.scalar(select(Order).options(selectinload(Order.items)).where(Order.id == order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if order.status in {"delivered", "cancelled"}:
        raise HTTPException(status_code=409, detail="Заказ уже завершён")
    if payload.status == "cancelled" and order.status == "shipped":
        raise HTTPException(
            status_code=409,
            detail="Отменить уже отправленный заказ нельзя; обработайте возврат отдельно",
        )
    if payload.status in {"processing", "shipped", "delivered"} and order.payment_status != "paid":
        raise HTTPException(status_code=409, detail="Нельзя обрабатывать неоплаченный заказ")
    if payload.status == "cancelled":
        if order.payment_status == "paid":
            raise HTTPException(
                status_code=409,
                detail="Оплаченный заказ нельзя отменить без оформления возврата",
            )
        if order.yookassa_payment_id and order.payment_status == "pending":
            raise HTTPException(
                status_code=409,
                detail="Сначала завершите или отмените платёж в ЮKassa",
            )
        restore_order_inventory(db, order)
    order.status = payload.status
    db.commit()
    db.refresh(order)
    return order


@app.post("/api/admin/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, _: AdminUser, db: DbSession) -> Product:
    if db.get(Category, payload.category_id) is None:
        raise HTTPException(status_code=422, detail="Категория не найдена")
    values = payload.model_dump(mode="python")
    values["stock_by_size"] = values["stock_by_size"] or distributed_stock(
        values["stock_quantity"], values["sizes"]
    )
    if values["stock_by_size"].keys() - set(values["sizes"]):
        raise HTTPException(status_code=422, detail="Остатки указаны для неизвестного размера")
    values["stock_by_size"] = {
        size: values["stock_by_size"].get(size, 0) for size in values["sizes"]
    }
    values["stock_quantity"] = sum(values["stock_by_size"].values())
    values["image_urls"] = values["image_urls"] or (
        [values["image_url"]] if values["image_url"] else []
    )
    values["image_url"] = values["image_urls"][0] if values["image_urls"] else values["image_url"]
    product = Product(**values)
    if product.image_url is not None:
        product.image_url = str(product.image_url)
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Артикул или slug уже используется") from None
    return db.scalar(
        select(Product).options(joinedload(Product.category)).where(Product.id == product.id)
    )


@app.patch("/api/admin/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, _: AdminUser, db: DbSession) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    changes = payload.model_dump(exclude_unset=True, mode="python")
    if (
        "category_id" in changes
        and changes["category_id"] is not None
        and db.get(Category, changes["category_id"]) is None
    ):
        raise HTTPException(status_code=422, detail="Категория не найдена")
    next_sizes = changes.get("sizes", product.sizes or ["ONE SIZE"])
    if "stock_by_size" in changes:
        inventory = changes["stock_by_size"] or {}
        if inventory.keys() - set(next_sizes):
            raise HTTPException(status_code=422, detail="Остатки указаны для неизвестного размера")
        changes["stock_by_size"] = {size: inventory.get(size, 0) for size in next_sizes}
        changes["stock_quantity"] = sum(changes["stock_by_size"].values())
    elif "stock_quantity" in changes:
        changes["stock_by_size"] = distributed_stock(changes["stock_quantity"], next_sizes)
    elif "sizes" in changes:
        current_inventory = product_stock_by_size(product)
        changes["stock_by_size"] = {size: current_inventory.get(size, 0) for size in next_sizes}
        changes["stock_quantity"] = sum(changes["stock_by_size"].values())
    if "image_urls" in changes:
        changes["image_urls"] = changes["image_urls"] or (
            [changes.get("image_url", product.image_url)]
            if changes.get("image_url", product.image_url)
            else []
        )
        if "image_url" not in changes and changes["image_urls"]:
            changes["image_url"] = changes["image_urls"][0]
    elif "image_url" in changes:
        changes["image_urls"] = [changes["image_url"]] if changes["image_url"] else []
    for key, value in changes.items():
        setattr(product, key, str(value) if key == "image_url" and value is not None else value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Артикул или slug уже используется") from None
    return db.scalar(
        select(Product).options(joinedload(Product.category)).where(Product.id == product.id)
    )
