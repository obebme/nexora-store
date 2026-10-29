from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('customer', 'admin')", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        String(20), default="customer", server_default=text("'customer'")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    verification_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cart: Mapped[Cart | None] = relationship(back_populates="user", uselist=False)
    orders: Mapped[list[Order]] = relationship(back_populates="user")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    products: Mapped[list[Product]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_products_price_nonnegative"),
        CheckConstraint("stock_quantity >= 0", name="ck_products_stock_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency_code: Mapped[str] = mapped_column(String(3), default="RUB", server_default="RUB")
    stock_quantity: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    stock_by_size: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text)
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    color_name: Mapped[str | None] = mapped_column(String(100))
    sizes: Mapped[list[str]] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    compare_at_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped[Category] = relationship(back_populates="products")

    @property
    def effective_stock_by_size(self) -> dict[str, int]:
        if self.stock_by_size is not None:
            return self.stock_by_size
        sizes = list(dict.fromkeys(self.sizes or ["ONE SIZE"]))
        quotient, remainder = divmod(self.stock_quantity, len(sizes))
        return {
            size: quotient + (1 if index < remainder else 0) for index, size in enumerate(sizes)
        }


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="cart")
    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart", cascade="all, delete-orphan"
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint(
            "cart_id", "product_id", "selected_size", name="uq_cart_items_cart_product_size"
        ),
        CheckConstraint("quantity > 0", name="ck_cart_items_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    selected_size: Mapped[str] = mapped_column(
        String(24), default="ONE SIZE", server_default="ONE SIZE"
    )
    quantity: Mapped[int] = mapped_column(default=1, server_default=text("1"))

    cart: Mapped[Cart] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'shipped', 'delivered', 'cancelled')",
            name="ck_orders_status",
        ),
        CheckConstraint(
            "payment_status IN ('pending', 'paid', 'failed', 'refunded')",
            name="ck_orders_payment_status",
        ),
        CheckConstraint(
            "refund_status IS NULL OR refund_status IN ('pending', 'succeeded', 'canceled')",
            name="ck_orders_refund_status",
        ),
        CheckConstraint("total_amount >= 0", name="ck_orders_total_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default=text("'pending'")
    )
    payment_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default=text("'pending'")
    )
    yookassa_payment_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    payment_confirmation_url: Mapped[str | None] = mapped_column(Text)
    payment_idempotence_key: Mapped[str | None] = mapped_column(String(36))
    payment_cancel_idempotence_key: Mapped[str | None] = mapped_column(String(36))
    yookassa_refund_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    refund_idempotence_key: Mapped[str | None] = mapped_column(String(36))
    refund_status: Mapped[str | None] = mapped_column(String(20))
    reservation_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency_code: Mapped[str] = mapped_column(String(3))
    shipping_name: Mapped[str] = mapped_column(String(160))
    shipping_address_line1: Mapped[str] = mapped_column(String(200))
    shipping_address_line2: Mapped[str | None] = mapped_column(String(200))
    shipping_city: Mapped[str] = mapped_column(String(120))
    shipping_region: Mapped[str | None] = mapped_column(String(120))
    shipping_postal_code: Mapped[str] = mapped_column(String(32))
    shipping_country_code: Mapped[str] = mapped_column(String(2))
    shipping_phone: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_price_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    product_name: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(64))
    selected_size: Mapped[str | None] = mapped_column(String(24))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantity: Mapped[int] = mapped_column()

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()
