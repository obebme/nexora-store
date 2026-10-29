from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    AliasPath,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

ShortPassword = Annotated[str, StringConstraints(min_length=10, max_length=128)]


def validate_product_image_url(value: str) -> str:
    if value.startswith(("/images/", "/uploads/")) and ".." not in value.split("/"):
        return value
    parsed = urlsplit(value)
    if parsed.scheme == "https" and parsed.netloc:
        return value
    raise ValueError("Нужен HTTPS-адрес фото или локальный путь /images/... или /uploads/...")


class UserCreate(BaseModel):
    email: EmailStr
    password: ShortPassword


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    model_config = ConfigDict(from_attributes=True)


class EmailOnly(BaseModel):
    email: EmailStr


class EmailActionOut(BaseModel):
    message: str


class EmailVerificationOut(BaseModel):
    email: EmailStr
    verified: bool
    notification_sent: bool
    message: str


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    new_password: ShortPassword


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GoogleOAuthConfigOut(BaseModel):
    client_id: str
    redirect_uri: str


class GoogleCodeExchange(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    code_verifier: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9._~-]+$")
    nonce: str = Field(min_length=32, max_length=128)


class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None
    model_config = ConfigDict(from_attributes=True)


class ProductOut(BaseModel):
    id: int
    category_id: int
    category: CategoryOut
    sku: str
    name: str
    slug: str
    description: str | None
    price: Decimal
    compare_at_price: Decimal | None
    currency_code: str
    stock_quantity: int
    stock_by_size: dict[str, int] = Field(
        default_factory=dict, validation_alias="effective_stock_by_size"
    )
    image_url: str | None
    image_urls: list[str] = Field(default_factory=list)
    color_name: str | None
    sizes: list[str]
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

    @field_validator("stock_by_size", mode="before")
    @classmethod
    def default_size_stock(cls, value: dict[str, int] | None) -> dict[str, int]:
        return value or {}

    @field_validator("image_urls", mode="before")
    @classmethod
    def default_image_urls(cls, value: list[str] | None) -> list[str]:
        return value or []


class ProductCreate(BaseModel):
    category_id: int
    sku: Annotated[str, Field(min_length=2, max_length=64)]
    name: Annotated[str, Field(min_length=2, max_length=200)]
    slug: Annotated[str, Field(min_length=2, max_length=220, pattern=r"^[a-z0-9-]+$")]
    description: str | None = None
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    compare_at_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency_code: Literal["RUB"] = "RUB"
    stock_quantity: int = Field(default=0, ge=0)
    stock_by_size: dict[str, int] | None = None
    image_url: str | None = Field(default=None, max_length=2048)
    image_urls: list[str] = Field(default_factory=list, max_length=10)
    color_name: str | None = Field(default=None, max_length=100)
    sizes: list[str] = Field(default_factory=lambda: ["ONE SIZE"], min_length=1, max_length=20)
    is_active: bool = True

    @field_validator("stock_by_size")
    @classmethod
    def validate_stock_by_size(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is not None and any(not size or count < 0 for size, count in value.items()):
            raise ValueError("Остаток по размеру должен быть неотрицательным.")
        return value

    @field_validator("sizes")
    @classmethod
    def validate_sizes(cls, value: list[str]) -> list[str]:
        if any(not size.strip() for size in value) or len(set(value)) != len(value):
            raise ValueError("Размеры должны быть непустыми и уникальными.")
        return value

    @field_validator("image_urls")
    @classmethod
    def validate_image_urls(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Фотографии не должны повторяться.")
        for image_url in value:
            validate_product_image_url(image_url)
        return value

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str | None) -> str | None:
        return validate_product_image_url(value) if value is not None else None


class ProductUpdate(BaseModel):
    category_id: int | None = None
    sku: Annotated[str | None, Field(min_length=2, max_length=64)] = None
    name: Annotated[str | None, Field(min_length=2, max_length=200)] = None
    slug: Annotated[str | None, Field(min_length=2, max_length=220, pattern=r"^[a-z0-9-]+$")] = None
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    compare_at_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency_code: Literal["RUB"] | None = None
    stock_quantity: int | None = Field(default=None, ge=0)
    stock_by_size: dict[str, int] | None = None
    image_url: str | None = Field(default=None, max_length=2048)
    image_urls: list[str] | None = Field(default=None, max_length=10)
    color_name: str | None = Field(default=None, max_length=100)
    sizes: list[str] | None = Field(default=None, min_length=1, max_length=20)
    is_active: bool | None = None

    @field_validator("stock_by_size")
    @classmethod
    def validate_stock_by_size(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is not None and any(not size or count < 0 for size, count in value.items()):
            raise ValueError("Остаток по размеру должен быть неотрицательным.")
        return value

    @field_validator("sizes")
    @classmethod
    def validate_sizes(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and (
            any(not size.strip() for size in value) or len(set(value)) != len(value)
        ):
            raise ValueError("Размеры должны быть непустыми и уникальными.")
        return value

    @field_validator("image_urls")
    @classmethod
    def validate_image_urls(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(set(value)) != len(value):
            raise ValueError("Фотографии не должны повторяться.")
        for image_url in value:
            validate_product_image_url(image_url)
        return value

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str | None) -> str | None:
        return validate_product_image_url(value) if value is not None else None


class CartItemCreate(BaseModel):
    product_id: int
    selected_size: str = Field(default="ONE SIZE", min_length=1, max_length=24)
    quantity: int = Field(default=1, ge=1, le=20)


class CartReplace(BaseModel):
    items: list[CartItemCreate] = Field(max_length=100)


class CartItemOut(BaseModel):
    product_id: int
    name: str
    slug: str
    sku: str
    selected_size: str
    quantity: int
    size_stock_quantity: int
    unit_price: Decimal
    image_url: str | None
    line_total: Decimal


class CartOut(BaseModel):
    items: list[CartItemOut]
    item_count: int
    total_amount: Decimal
    currency_code: str = "RUB"


class ShippingAddress(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    address_line1: str = Field(min_length=3, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=2, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    postal_code: str = Field(min_length=2, max_length=32)
    country_code: Literal["RU"]
    phone: str | None = Field(default=None, max_length=32)


class OrderCreate(BaseModel):
    shipping: ShippingAddress


class OrderItemOut(BaseModel):
    product_id: int | None
    product_name: str
    sku: str
    selected_size: str | None
    unit_price: Decimal
    quantity: int


class OrderOut(BaseModel):
    id: int
    status: str
    payment_status: str
    refund_status: str | None = None
    reservation_expires_at: datetime | None = None
    total_amount: Decimal
    currency_code: str
    items: list[OrderItemOut]
    created_at: datetime
    shipping_name: str | None = None
    shipping_address_line1: str | None = None
    shipping_address_line2: str | None = None
    shipping_city: str | None = None
    shipping_region: str | None = None
    shipping_postal_code: str | None = None
    shipping_country_code: str | None = None
    shipping_phone: str | None = None

    model_config = ConfigDict(from_attributes=True)

    customer_email: str | None = Field(default=None, validation_alias=AliasPath("user", "email"))


class PaymentConfirmationOut(BaseModel):
    confirmation_url: str


class YooKassaWebhookObject(BaseModel):
    id: str = Field(min_length=1, max_length=64)


class YooKassaWebhook(BaseModel):
    event: Literal[
        "payment.succeeded",
        "payment.canceled",
        "refund.succeeded",
        "refund.canceled",
    ]
    object: YooKassaWebhookObject


class OrderStatusUpdate(BaseModel):
    status: Literal["processing", "shipped", "delivered", "cancelled"]
