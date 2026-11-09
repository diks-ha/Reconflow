from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class OrderReconciliationInput(BaseModel):
    order_id: str = Field(min_length=1, max_length=120)
    expected_amount: Decimal | None = None
    payment_method: str | None = None
    order_value: Decimal | None = None
    channel: str | None = None
    delivery_status: str | None = None
    settlement_due_date: date | None = None
    payment_eligible: bool = False
    return_status: str | None = None
    return_id: str | None = None
    return_deadline: date | None = None
    tracking_id: str | None = None
    source_import_id: UUID | None = None
    source_row_number: int | None = None
    raw_source: dict = Field(default_factory=dict)
    partner_id: UUID | None = None


class PaymentReconciliationInput(BaseModel):
    order_id: str
    amount: Decimal
    transaction_id: str | None = None
    partner_id: str | None = None
    gst_tcs: Decimal = Decimal("0.00")
    income_tax_tds: Decimal = Decimal("0.00")
    source_import_id: UUID | None = None
    source_row_number: int | None = None


class FreightReconciliationInput(BaseModel):
    order_id: str
    billed_charge: Decimal
    channel: str | None = None
    courier_partner: str | None = None
    weight: Decimal | None = None
    tracking_id: str | None = None
    transaction_id: str | None = None
    partner_id: str | None = None
    source_import_id: UUID | None = None
    source_row_number: int | None = None


class RateCardInput(BaseModel):
    channel: str
    courier_partner: str
    min_weight: Decimal
    max_weight: Decimal | None = None
    forward_fee: Decimal
    return_fee: Decimal = Decimal("0.00")
    cod_fee: Decimal = Decimal("0.00")
    fixed_charge: Decimal = Decimal("0.00")
    percentage_charge: Decimal = Decimal("0.0000")
    effective_from: date = date.min
    effective_to: date | None = None
    is_active: bool = True


class WarehouseReceiptInput(BaseModel):
    order_id: str
    received_at: date | None = None
    return_id: str | None = None
    tracking_id: str | None = None
    source_import_id: UUID | None = None
    source_row_number: int | None = None


class ReconciliationRunRequest(BaseModel):
    import_ids: list[UUID] | None = Field(default=None, min_length=1)
    orders: list[OrderReconciliationInput] = Field(default_factory=list)
    settlements: list[PaymentReconciliationInput] = Field(default_factory=list)
    cod_remittances: list[PaymentReconciliationInput] = Field(default_factory=list)
    freight_invoices: list[FreightReconciliationInput] = Field(default_factory=list)
    warehouse_receipts: list[WarehouseReceiptInput] = Field(default_factory=list)
    rate_cards: list[RateCardInput] = Field(default_factory=list)
    as_of: date = Field(default_factory=date.today)
    threshold: Decimal = Decimal("10.00")

    @model_validator(mode="after")
    def require_input_data(self):
        if not self.import_ids and not self.orders:
            raise ValueError("Provide processed import_ids or at least one order")
        return self


class ReconciliationRunResponse(BaseModel):
    run_id: UUID
    status: str
    results_count: int
    claims_created: int
    summary: dict

