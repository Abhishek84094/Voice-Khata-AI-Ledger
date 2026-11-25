"""SQLAlchemy 2 declarative database models (§5.1).

All tables enforce strict per-shop isolation (shop_id).
All sensitive fields (names, amounts, notes, phone) are encrypted at rest.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="hi-IN", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    users: Mapped[list[User]] = relationship(
        "User", back_populates="shop", cascade="all, delete-orphan"
    )
    customers: Mapped[list[Customer]] = relationship(
        "Customer", back_populates="shop", cascade="all, delete-orphan"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    shop_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=False
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="owner", nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="hi-IN", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    shop: Mapped[Shop] = relationship("Shop", back_populates="users")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    shop_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=False
    )
    display_name_enc: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # Encrypted original script name
    search_key: Mapped[str] = mapped_column(
        String(255), index=True, nullable=False
    )  # Transliterated ASCII
    aliases_enc: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )  # Encrypted JSON list of aliases
    phone_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # Optional encrypted phone
    reminder_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    shop: Mapped[Shop] = relationship("Shop", back_populates="customers")
    events: Mapped[list[LedgerEvent]] = relationship(
        "LedgerEvent", back_populates="customer", cascade="all, delete-orphan"
    )
    promises: Mapped[list[Promise]] = relationship(
        "Promise", back_populates="customer", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_customers_shop_search", "shop_id", "search_key"),)


class LedgerEvent(Base):
    __tablename__ = "ledger_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    shop_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # CREDIT_GIVEN, PAYMENT_RECEIVED, AMENDED, VOIDED
    amount_paise_enc: Mapped[str] = mapped_column(Text, nullable=False)  # Encrypted integer paise
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    source_utterance_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    target_event_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )  # For AMENDED / VOIDED
    note_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # Encrypted shopkeeper memo

    customer: Mapped[Customer] = relationship("Customer", back_populates="events")

    __table_args__ = (
        UniqueConstraint("shop_id", "idempotency_key", name="uq_ledger_events_shop_idempotency"),
        Index("ix_ledger_events_shop_customer", "shop_id", "customer_id", "recorded_at"),
    )


class CustomerBalance(Base):
    __tablename__ = "customer_balances"

    shop_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True
    )
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True
    )
    balance_paise: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )  # Integer paise
    last_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (Index("ix_customer_balances_shop", "shop_id"),)


class Promise(Base):
    __tablename__ = "promises"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    shop_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount_paise_enc: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Null = whole balance
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="OPEN", nullable=False
    )  # OPEN, PARTIALLY_KEPT, KEPT, BROKEN, RESCHEDULED, CANCELLED
    source_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    customer: Mapped[Customer] = relationship("Customer", back_populates="promises")

    __table_args__ = (Index("ix_promises_shop_due", "shop_id", "due_date", "status"),)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    shop_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    details_enc: Mapped[str] = mapped_column(Text, default="", nullable=False)
