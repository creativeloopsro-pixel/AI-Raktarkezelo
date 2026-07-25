from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from secrets import token_hex
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_routing_token() -> str:
    return token_hex(12)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    users: Mapped[list[User]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_user_org_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(254))
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="warehouse")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    organization: Mapped[Organization] = relationship(back_populates="users")


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("organization_id", "internal_sku", name="uq_product_org_sku"),
        Index("ix_product_org_name", "organization_id", "name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    internal_sku: Mapped[str] = mapped_column(String(80))
    base_unit: Mapped[str] = mapped_column(String(24), default="piece")
    status: Mapped[str] = mapped_column(String(24), default="active")
    min_stock: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    packaging_units: Mapped[list[PackagingUnit]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    barcodes: Mapped[list[ProductBarcode]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    external_mappings: Mapped[list[ExternalProductMapping]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    balance: Mapped[StockBalance | None] = relationship(back_populates="product")


class PackagingUnit(Base):
    __tablename__ = "packaging_units"
    __table_args__ = (UniqueConstraint("product_id", "name", name="uq_packaging_product_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    multiplier_to_base_unit: Mapped[Decimal] = mapped_column(Numeric(18, 3))

    product: Mapped[Product] = relationship(back_populates="packaging_units")
    barcodes: Mapped[list[ProductBarcode]] = relationship(back_populates="packaging_unit")


class ProductBarcode(Base):
    __tablename__ = "product_barcodes"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_barcode_org_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    packaging_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("packaging_units.id", ondelete="SET NULL"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(128))
    symbology: Mapped[str] = mapped_column(String(32), default="EAN_13")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    product: Mapped[Product] = relationship(back_populates="barcodes")
    packaging_unit: Mapped[PackagingUnit | None] = relationship(back_populates="barcodes")


class StockBalance(Base):
    __tablename__ = "stock_balances"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    product: Mapped[Product] = relationship(back_populates="balance")


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_movement_org_idempotency"),
        Index("ix_movement_org_product_created", "organization_id", "product_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    movement_type: Mapped[str] = mapped_column(String(40))
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    source_type: Mapped[str] = mapped_column(String(60))
    source_id: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(160))
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reverses_movement_id: Mapped[str | None] = mapped_column(
        ForeignKey("stock_movements.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InventorySession(Base):
    __tablename__ = "inventory_sessions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "client_session_id",
            name="uq_inventory_session_org_client",
        ),
        Index(
            "ix_inventory_session_org_status",
            "organization_id",
            "status",
            "started_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    client_session_id: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    started_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("review_tasks.id", ondelete="SET NULL"), nullable=True
    )
    completion_note: Mapped[str | None] = mapped_column(
        String(1000), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    counts: Mapped[list[InventoryCount]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    corrections: Mapped[list[InventoryStockCorrection]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class InventoryCount(Base):
    __tablename__ = "inventory_counts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "client_operation_id",
            name="uq_inventory_count_org_operation",
        ),
        Index(
            "ix_inventory_count_session_product_recorded",
            "session_id",
            "product_id",
            "client_recorded_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_sessions.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    client_operation_id: Mapped[str] = mapped_column(String(80))
    expected_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    client_expected_quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 3), nullable=True
    )
    counted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    quantity_difference: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    scanned_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    reason_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    client_recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    session: Mapped[InventorySession] = relationship(back_populates="counts")
    product: Mapped[Product] = relationship()
    correction: Mapped[InventoryStockCorrection | None] = relationship(
        back_populates="count"
    )


class InventoryStockCorrection(Base):
    __tablename__ = "stock_corrections"
    __table_args__ = (
        UniqueConstraint("count_id", name="uq_stock_correction_count"),
        Index(
            "ix_stock_correction_org_created",
            "organization_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_sessions.id", ondelete="CASCADE"), index=True
    )
    count_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_counts.id", ondelete="RESTRICT"), index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    movement_id: Mapped[str] = mapped_column(
        ForeignKey("stock_movements.id", ondelete="RESTRICT"), unique=True
    )
    expected_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    counted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    reason_code: Mapped[str] = mapped_column(String(60))
    reason_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    session: Mapped[InventorySession] = relationship(
        back_populates="corrections"
    )
    count: Mapped[InventoryCount] = relationship(back_populates="correction")
    product: Mapped[Product] = relationship()
    movement: Mapped[StockMovement] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_org_created", "organization_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(128))
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("organization_id", "sha256_hash", name="uq_document_org_hash"),
        Index("ix_document_org_status_created", "organization_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256_hash: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="UPLOADED")
    source_type: Mapped[str] = mapped_column(String(40), default="WEB_UPLOAD")
    document_type: Mapped[str] = mapped_column(String(60), default="goods_receipt")
    page_count: Mapped[int] = mapped_column(default=0)
    validation_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    uploaded_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    processing_jobs: Mapped[list[DocumentProcessingJob]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_document_page_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int]
    status: Mapped[str] = mapped_column(String(32), default="REGISTERED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped[Document] = relationship(back_populates="pages")


class EmailInboundSettings(Base):
    __tablename__ = "email_inbound_settings"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    routing_token: Mapped[str] = mapped_column(
        String(48), unique=True, index=True, default=new_routing_token
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_process: Mapped[bool] = mapped_column(Boolean, default=True)
    allowed_sender_domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class InboundEmail(Base):
    __tablename__ = "inbound_emails"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "provider_message_id",
            name="uq_inbound_email_org_provider_message",
        ),
        Index(
            "ix_inbound_email_org_status_received",
            "organization_id",
            "status",
            "received_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    provider_message_id: Mapped[str] = mapped_column(String(255))
    sender: Mapped[str] = mapped_column(String(254))
    recipients: Mapped[list[str]] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(32), default="PROCESSING")
    attachment_count: Mapped[int] = mapped_column(default=0)
    accepted_count: Mapped[int] = mapped_column(default=0)
    duplicate_count: Mapped[int] = mapped_column(default=0)
    rejected_count: Mapped[int] = mapped_column(default=0)
    error_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    attachments: Mapped[list[InboundEmailAttachment]] = relationship(
        back_populates="email",
        cascade="all, delete-orphan",
        order_by="InboundEmailAttachment.position",
    )


class InboundEmailAttachment(Base):
    __tablename__ = "inbound_email_attachments"
    __table_args__ = (
        UniqueConstraint("email_id", "position", name="uq_inbound_attachment_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email_id: Mapped[str] = mapped_column(
        ForeignKey("inbound_emails.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    filename: Mapped[str] = mapped_column(String(255))
    declared_content_type: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32))
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rejection_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    email: Mapped[InboundEmail] = relationship(back_populates="attachments")
    document: Mapped[Document | None] = relationship()


class Plugin(Base):
    __tablename__ = "plugins"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "plugin_key", name="uq_plugin_org_key"
        ),
        Index("ix_plugin_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    plugin_key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(24), default="DISABLED")
    active_version: Mapped[str] = mapped_column(String(40))
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    service_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    installed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    enabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    versions: Mapped[list[PluginVersion]] = relationship(
        back_populates="plugin", cascade="all, delete-orphan"
    )
    permissions: Mapped[list[PluginPermission]] = relationship(
        back_populates="plugin", cascade="all, delete-orphan"
    )
    settings: Mapped[list[PluginSetting]] = relationship(
        back_populates="plugin", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[PluginJob]] = relationship(back_populates="plugin")
    service_user: Mapped[User] = relationship(foreign_keys=[service_user_id])


class PluginVersion(Base):
    __tablename__ = "plugin_versions"
    __table_args__ = (
        UniqueConstraint("plugin_id", "version", name="uq_plugin_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    plugin_id: Mapped[str] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(40))
    api_version: Mapped[str] = mapped_column(String(20))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    installed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    plugin: Mapped[Plugin] = relationship(back_populates="versions")


class PluginPermission(Base):
    __tablename__ = "plugin_permissions"
    __table_args__ = (
        UniqueConstraint(
            "plugin_id", "permission", name="uq_plugin_permission"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    plugin_id: Mapped[str] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), index=True
    )
    permission: Mapped[str] = mapped_column(String(100))
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    plugin: Mapped[Plugin] = relationship(back_populates="permissions")


class PluginSetting(Base):
    __tablename__ = "plugin_settings"
    __table_args__ = (
        UniqueConstraint("plugin_id", "setting_key", name="uq_plugin_setting_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    plugin_id: Mapped[str] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), index=True
    )
    setting_key: Mapped[str] = mapped_column(String(100))
    value: Mapped[Any] = mapped_column(JSON)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    plugin: Mapped[Plugin] = relationship(back_populates="settings")


class PluginJob(Base):
    __tablename__ = "plugin_jobs"
    __table_args__ = (
        UniqueConstraint(
            "plugin_id", "outbox_event_id", name="uq_plugin_job_event"
        ),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_plugin_job_org_idempotency",
        ),
        Index(
            "ix_plugin_job_status_due",
            "status",
            "next_attempt_at",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    plugin_id: Mapped[str] = mapped_column(
        ForeignKey("plugins.id", ondelete="RESTRICT"), index=True
    )
    outbox_event_id: Mapped[str] = mapped_column(
        ForeignKey("outbox_events.id", ondelete="CASCADE"), index=True
    )
    plugin_version: Mapped[str] = mapped_column(String(40))
    event_type: Mapped[str] = mapped_column(String(100))
    aggregate_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    plugin: Mapped[Plugin] = relationship(back_populates="jobs")


class DocumentProcessingJob(Base):
    __tablename__ = "document_processing_jobs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_document_job_org_idempotency"
        ),
        Index("ix_document_job_org_status_created", "organization_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(160))
    job_type: Mapped[str] = mapped_column(String(60), default="AI_EXTRACTION")
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    attempts: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped[Document] = relationship(back_populates="processing_jobs")
    ai_requests: Mapped[list[AiRequest]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class AiRequest(Base):
    __tablename__ = "ai_requests"
    __table_args__ = (
        Index("ix_ai_request_org_status_created", "organization_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("document_processing_jobs.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    model_name: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    response_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[DocumentProcessingJob] = relationship(back_populates="ai_requests")
    result: Mapped[AiResult | None] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class AiResult(Base):
    __tablename__ = "ai_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[str] = mapped_column(
        ForeignKey("ai_requests.id", ondelete="CASCADE"), unique=True, index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    normalized_output: Mapped[dict[str, Any]] = mapped_column(JSON)
    overall_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    response_hash: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    request: Mapped[AiRequest] = relationship(back_populates="result")
    tool_calls: Mapped[list[AiToolCall]] = relationship(
        back_populates="result", cascade="all, delete-orphan"
    )
    receipt_draft: Mapped[GoodsReceiptDraft | None] = relationship(
        back_populates="ai_result", cascade="all, delete-orphan"
    )


class AiToolCall(Base):
    __tablename__ = "ai_tool_calls"
    __table_args__ = (
        Index("ix_ai_tool_call_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    ai_result_id: Mapped[str] = mapped_column(
        ForeignKey("ai_results.id", ondelete="CASCADE"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(100))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    result: Mapped[AiResult] = relationship(back_populates="tool_calls")


class GoodsReceiptDraft(Base):
    __tablename__ = "goods_receipt_drafts"
    __table_args__ = (
        Index("ix_receipt_draft_org_status_created", "organization_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), unique=True, index=True
    )
    ai_result_id: Mapped[str] = mapped_column(
        ForeignKey("ai_results.id", ondelete="CASCADE"), unique=True, index=True
    )
    document_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="NEEDS_REVIEW")
    validation_issues: Mapped[list[str]] = mapped_column(JSON, default=list)
    confirmed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ai_result: Mapped[AiResult] = relationship(back_populates="receipt_draft")
    items: Mapped[list[GoodsReceiptItem]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        order_by="GoodsReceiptItem.line_number",
    )


class GoodsReceiptItem(Base):
    __tablename__ = "goods_receipt_items"
    __table_args__ = (
        UniqueConstraint("draft_id", "line_number", name="uq_receipt_item_line"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    draft_id: Mapped[str] = mapped_column(
        ForeignKey("goods_receipt_drafts.id", ondelete="CASCADE"), index=True
    )
    line_number: Mapped[int]
    description: Mapped[str] = mapped_column(String(500))
    barcode: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    unit: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    source_page: Mapped[int]
    matched_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    packaging_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("packaging_units.id", ondelete="RESTRICT"), nullable=True
    )
    conversion_factor: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    base_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    match_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="NEEDS_REVIEW")
    validation_issues: Mapped[list[str]] = mapped_column(JSON, default=list)

    draft: Mapped[GoodsReceiptDraft] = relationship(back_populates="items")
    matched_product: Mapped[Product | None] = relationship()
    packaging_unit: Mapped[PackagingUnit | None] = relationship()


class ExternalProductMapping(Base):
    __tablename__ = "external_product_mappings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "plugin_id",
            "external_key",
            name="uq_external_mapping_org_plugin_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    plugin_id: Mapped[str] = mapped_column(String(80), default="vrp-import")
    external_key: Mapped[str] = mapped_column(String(320))
    external_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    external_name: Mapped[str] = mapped_column(String(255))
    normalized_external_name: Mapped[str] = mapped_column(String(255), index=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    conversion_factor: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), default=Decimal("1")
    )
    confirmed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    product: Mapped[Product] = relationship(back_populates="external_mappings")


class VrpImportSchedule(Base):
    __tablename__ = "vrp_import_schedules"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    frequency: Mapped[str] = mapped_column(String(20), default="DAILY")
    processing_time: Mapped[time] = mapped_column(Time, default=time(23, 55))
    timezone: Mapped[str] = mapped_column(String(80), default="Europe/Bratislava")
    weekly_day: Mapped[str] = mapped_column(String(16), default="SUNDAY")
    monthly_rule: Mapped[str] = mapped_column(String(16), default="LAST_DAY")
    auto_process: Mapped[bool] = mapped_column(Boolean, default=False)
    unknown_product_policy: Mapped[str] = mapped_column(String(32), default="STOP")
    negative_stock_policy: Mapped[str] = mapped_column(
        String(32), default="ALLOW_WITH_WARNING"
    )
    overlap_policy: Mapped[str] = mapped_column(String(20), default="BLOCK")
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class VrpImportBatch(Base):
    __tablename__ = "vrp_import_batches"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "file_hash",
            name="uq_vrp_batch_org_file_hash",
        ),
        UniqueConstraint(
            "organization_id",
            "canonical_items_hash",
            name="uq_vrp_batch_org_canonical_hash",
        ),
        UniqueConstraint(
            "organization_id",
            "external_report_id",
            name="uq_vrp_batch_org_external_report",
        ),
        Index(
            "ix_vrp_batch_org_status_scheduled",
            "organization_id",
            "status",
            "scheduled_for",
        ),
        Index(
            "ix_vrp_batch_org_period",
            "organization_id",
            "period_start",
            "period_end",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    object_key: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    canonical_items_hash: Mapped[str] = mapped_column(String(64), index=True)
    parser_version: Mapped[str] = mapped_column(String(40))
    external_report_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="UPLOADED")
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    uploaded_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    processed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reversed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    items: Mapped[list[VrpImportItem]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="VrpImportItem.line_number",
    )
    errors: Mapped[list[VrpImportError]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="VrpImportError.line_number",
    )


class VrpImportItem(Base):
    __tablename__ = "vrp_import_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "line_number", name="uq_vrp_item_batch_line"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("vrp_import_batches.id", ondelete="CASCADE"), index=True
    )
    line_number: Mapped[int]
    external_product_id: Mapped[str | None] = mapped_column(
        String(160), nullable=True
    )
    external_name: Mapped[str] = mapped_column(String(255))
    normalized_external_name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    unit: Mapped[str] = mapped_column(String(80), default="piece")
    matched_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    conversion_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 3), nullable=True
    )
    base_quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 3), nullable=True
    )
    match_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="NEEDS_REVIEW")
    validation_issues: Mapped[list[str]] = mapped_column(JSON, default=list)

    batch: Mapped[VrpImportBatch] = relationship(back_populates="items")
    matched_product: Mapped[Product | None] = relationship()


class VrpImportError(Base):
    __tablename__ = "vrp_import_errors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("vrp_import_batches.id", ondelete="CASCADE"), index=True
    )
    line_number: Mapped[int | None] = mapped_column(nullable=True)
    error_code: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(String(500))
    raw_row: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    batch: Mapped[VrpImportBatch] = relationship(back_populates="errors")


class ReviewTask(Base):
    __tablename__ = "review_tasks"
    __table_args__ = (
        Index("ix_review_org_status_created", "organization_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    task_type: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(128), index=True)
    reason_code: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    assigned_to: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_unpublished", "published_at", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(100))
    aggregate_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
