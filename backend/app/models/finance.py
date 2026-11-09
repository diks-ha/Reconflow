from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, JSON, Numeric, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base

MONEY = Numeric(14, 2, asdecimal=True)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("channel", "order_id", name="uq_orders_channel_order"),
        Index("ix_orders_partner_order", "partner_id", "order_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    partner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False)
    channel: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    payment_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    order_value: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    expected_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    settlement_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    return_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    return_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    return_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    tracking_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    raw_source: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_import_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("imports.id", ondelete="RESTRICT"), nullable=False)
    source_row_number: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Settlement(Base):
    __tablename__ = "settlements"
    __table_args__ = (
        UniqueConstraint("partner_id", "transaction_id", name="uq_settlement_partner_transaction"),
        UniqueConstraint("source_import_id", "source_row_number", name="uq_settlement_import_row"),
        Index("ix_settlements_order", "order_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False)
    order_id: Mapped[str] = mapped_column(String(120), nullable=False)
    transaction_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    gst_tcs: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    income_tax_tds: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    settled_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_import_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("imports.id", ondelete="RESTRICT"), nullable=False)
    source_row_number: Mapped[int] = mapped_column(nullable=False)
    raw_source: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class CodRemittance(Base):
    __tablename__ = "cod_remittances"
    __table_args__ = (
        UniqueConstraint("partner_id", "transaction_id", name="uq_cod_partner_transaction"),
        UniqueConstraint("source_import_id", "source_row_number", name="uq_cod_import_row"),
        Index("ix_cod_remittances_order", "order_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False)
    order_id: Mapped[str] = mapped_column(String(120), nullable=False)
    transaction_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    remitted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_import_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("imports.id", ondelete="RESTRICT"), nullable=False)
    source_row_number: Mapped[int] = mapped_column(nullable=False)
    raw_source: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class FreightInvoice(Base):
    __tablename__ = "freight_invoices"
    __table_args__ = (
        UniqueConstraint("partner_id", "transaction_id", name="uq_freight_partner_transaction"),
        UniqueConstraint("source_import_id", "source_row_number", name="uq_freight_import_row"),
        Index("ix_freight_invoices_order", "order_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False)
    order_id: Mapped[str] = mapped_column(String(120), nullable=False)
    transaction_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tracking_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    courier_partner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    billed_charge: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 3, asdecimal=True), nullable=True)
    source_import_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("imports.id", ondelete="RESTRICT"), nullable=False)
    source_row_number: Mapped[int] = mapped_column(nullable=False)
    raw_source: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class WarehouseReceipt(Base):
    __tablename__ = "warehouse_receipts"
    __table_args__ = (
        UniqueConstraint("source_import_id", "source_row_number", name="uq_receipt_import_row"),
        Index("ix_warehouse_receipts_order", "order_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[str] = mapped_column(String(120), nullable=False)
    return_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    tracking_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    received_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_import_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("imports.id", ondelete="RESTRICT"), nullable=False)
    source_row_number: Mapped[int] = mapped_column(nullable=False)
    raw_source: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ReturnRecord(Base):
    __tablename__ = "returns"
    __table_args__ = (
        UniqueConstraint("partner_id", "return_id", name="uq_returns_partner_return"),
        UniqueConstraint("source_import_id", "source_row_number", name="uq_returns_import_row"),
        Index("ix_returns_order", "order_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False)
    order_id: Mapped[str] = mapped_column(String(120), nullable=False)
    return_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    return_status: Mapped[str] = mapped_column(String(60), nullable=False)
    courier_partner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tracking_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    initiated_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_import_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("imports.id", ondelete="RESTRICT"), nullable=False)
    source_row_number: Mapped[int] = mapped_column(nullable=False)
    raw_source: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class RateCard(Base):
    __tablename__ = "rate_cards"
    __table_args__ = (
        Index("ix_rate_cards_lookup", "channel", "courier_partner", "effective_from", "effective_to"),
        CheckConstraint("min_weight >= 0 AND (max_weight IS NULL OR max_weight >= min_weight)", name="ck_rate_card_weight_range"),
        CheckConstraint("forward_fee >= 0 AND return_fee >= 0 AND cod_fee >= 0 AND fixed_charge >= 0", name="ck_rate_card_fees_nonnegative"),
        CheckConstraint("percentage_charge >= 0", name="ck_rate_card_percentage_nonnegative"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_rate_card_effective_range"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    courier_partner: Mapped[str] = mapped_column(String(120), nullable=False)
    min_weight: Mapped[Decimal] = mapped_column(Numeric(12, 3, asdecimal=True), nullable=False)
    max_weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 3, asdecimal=True), nullable=True)
    forward_fee: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    return_fee: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    cod_fee: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    fixed_charge: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    percentage_charge: Mapped[Decimal] = mapped_column(Numeric(7, 4, asdecimal=True), nullable=False, default=Decimal("0.0000"))
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    source_note: Mapped[str] = mapped_column(String(120), nullable=False, default="Configured rate card")
    version_number: Mapped[int] = mapped_column(nullable=False, default=1)
    supersedes_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rate_cards.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class RateCardHistory(Base):
    __tablename__ = "rate_card_history"
    __table_args__ = (UniqueConstraint("rate_card_id", "version_number", name="uq_rate_card_history_version"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    rate_card_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("rate_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    changed_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    threshold: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("10.00"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="COMPLETED")
    summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"
    __table_args__ = (
        UniqueConstraint("run_id", "order_id", name="uq_reconciliation_run_order"),
        Index("ix_reconciliation_results_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False)
    partner_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("partners.id", ondelete="SET NULL"), nullable=True, index=True)
    order_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    received_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    difference: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    gst_tcs: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    income_tax_tds: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    findings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    explanation: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("order_id", "category", name="uq_claim_order_category"),
        CheckConstraint("recovered_amount >= 0 AND (amount IS NULL OR recovered_amount <= amount)", name="ck_claims_recovery_range"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    reconciliation_result_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("reconciliation_results.id", ondelete="RESTRICT"), nullable=False)
    partner_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("partners.id", ondelete="SET NULL"), nullable=True, index=True)
    order_id: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    recovered_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    assigned_reviewer_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    claim_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    source_import_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("imports.id", ondelete="SET NULL"), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_row_number: Mapped[int | None] = mapped_column(nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ClaimNote(Base):
    __tablename__ = "claim_notes"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    claim_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    note: Mapped[str] = mapped_column(String(4000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

