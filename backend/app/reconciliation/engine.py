from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

MONEY_QUANTUM = Decimal("0.01")
DEFAULT_THRESHOLD = Decimal("10.00")


def money(value: Decimal | str | int | None) -> Decimal | None:
    if value is None:
        return None
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Financial amounts must be finite decimal values")
    return result.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class OrderInput:
    order_id: str
    expected_amount: Decimal | None
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
    source_import_id: str | None = None
    source_row_number: int | None = None
    raw_source: dict = field(default_factory=dict)
    partner_id: str | None = None


@dataclass(frozen=True)
class PaymentInput:
    order_id: str
    amount: Decimal
    transaction_id: str | None = None
    partner_id: str | None = None
    gst_tcs: Decimal = Decimal("0.00")
    income_tax_tds: Decimal = Decimal("0.00")
    source_import_id: str | None = None
    source_row_number: int | None = None
    source_type: str = "settlement"


@dataclass(frozen=True)
class FreightInput:
    order_id: str
    billed_charge: Decimal
    channel: str | None
    courier_partner: str | None
    weight: Decimal | None
    tracking_id: str | None = None
    transaction_id: str | None = None
    partner_id: str | None = None
    source_import_id: str | None = None
    source_row_number: int | None = None


@dataclass(frozen=True)
class RateInput:
    channel: str
    courier_partner: str
    min_weight: Decimal
    max_weight: Decimal | None
    forward_fee: Decimal
    return_fee: Decimal = Decimal("0.00")
    cod_fee: Decimal = Decimal("0.00")
    fixed_charge: Decimal = Decimal("0.00")
    percentage_charge: Decimal = Decimal("0.0000")
    effective_from: date = date.min
    effective_to: date | None = None
    is_active: bool = True


@dataclass(frozen=True)
class WarehouseReceiptInput:
    order_id: str
    received_at: date | None
    return_id: str | None = None
    tracking_id: str | None = None
    source_import_id: str | None = None
    source_row_number: int | None = None


@dataclass
class Finding:
    category: str
    amount: Decimal | None
    explanation: str
    evidence: list[dict]
    confirmed: bool


@dataclass
class OrderResult:
    order_id: str
    status: str
    expected_amount: Decimal | None
    received_amount: Decimal | None
    difference: Decimal | None
    gst_tcs: Decimal
    income_tax_tds: Decimal
    findings: list[Finding]
    explanation: str
    evidence: list[dict]
    partner_id: str | None = None


@dataclass(frozen=True)
class ReconciliationInput:
    orders: list[OrderInput]
    settlements: list[PaymentInput] = field(default_factory=list)
    cod_remittances: list[PaymentInput] = field(default_factory=list)
    freight_invoices: list[FreightInput] = field(default_factory=list)
    warehouse_receipts: list[WarehouseReceiptInput] = field(default_factory=list)
    rate_cards: list[RateInput] = field(default_factory=list)
    as_of: date = date.today()
    threshold: Decimal = DEFAULT_THRESHOLD


def calculate_freight(rate: RateInput, *, order_value: Decimal | None, is_cod: bool, is_return: bool) -> Decimal:
    base_fee = rate.return_fee if is_return else rate.forward_fee
    cod_fee = rate.cod_fee if is_cod else Decimal("0.00")
    percentage_base = order_value or Decimal("0.00")
    return money(base_fee + rate.fixed_charge + cod_fee + percentage_base * rate.percentage_charge / Decimal("100")) or Decimal("0.00")


def _find_rate(invoice: FreightInput, cards: Iterable[RateInput], when: date) -> RateInput | None:
    if invoice.weight is None or invoice.channel is None or invoice.courier_partner is None:
        return None
    best: RateInput | None = None
    for card in cards:
        if not (
            card.is_active
            and card.channel.casefold() == invoice.channel.casefold()
            and card.courier_partner.casefold() == invoice.courier_partner.casefold()
            and card.min_weight <= invoice.weight
            and (card.max_weight is None or invoice.weight <= card.max_weight)
            and card.effective_from <= when
            and (card.effective_to is None or when <= card.effective_to)
        ):
            continue
        if best is None or (card.min_weight, card.effective_from) > (best.min_weight, best.effective_from):
            best = card
    return best


def reconcile(data: ReconciliationInput) -> list[OrderResult]:
    """Index joins in O(n+p+f+w+f*c), with c configured rate cards and f freight rows."""
    if money(data.threshold) is None or money(data.threshold) < 0:
        raise ValueError("Discrepancy threshold must be zero or greater")
    orders_by_id: dict[str, OrderInput] = {}
    for order in data.orders:
        if order.order_id in orders_by_id:
            raise ValueError(f"Duplicate order key in reconciliation input: {order.order_id}")
        orders_by_id[order.order_id] = order

    transaction_keys: set[tuple[str, str]] = set()
    source_rows: set[tuple[str, int]] = set()
    for record in [*data.settlements, *data.cod_remittances]:
        if record.transaction_id:
            key = (record.partner_id or record.source_type, record.transaction_id)
            if key in transaction_keys:
                raise ValueError(f"Duplicate transaction identifier in reconciliation input: {record.transaction_id}")
            transaction_keys.add(key)
        if record.source_import_id and record.source_row_number is not None:
            row_key = (record.source_import_id, record.source_row_number)
            if row_key in source_rows:
                raise ValueError("Duplicate source row included in payment inputs")
            source_rows.add(row_key)
    freight_ids: set[tuple[str, str]] = set()
    for record in data.freight_invoices:
        freight_key = (record.partner_id or record.courier_partner or "", record.transaction_id or "")
        if record.transaction_id and freight_key in freight_ids:
            raise ValueError(f"Duplicate freight transaction identifier: {record.transaction_id}")
        if record.transaction_id:
            freight_ids.add(freight_key)

    settlements: dict[str, list[PaymentInput]] = defaultdict(list)
    cods: dict[str, list[PaymentInput]] = defaultdict(list)
    freight: dict[str, list[FreightInput]] = defaultdict(list)
    receipts_by_order: dict[str, list[WarehouseReceiptInput]] = defaultdict(list)
    receipts_by_return: dict[str, list[WarehouseReceiptInput]] = defaultdict(list)
    receipts_by_tracking: dict[str, list[WarehouseReceiptInput]] = defaultdict(list)
    for record in data.settlements:
        settlements[record.order_id].append(record)
    for record in data.cod_remittances:
        cods[record.order_id].append(record)
    for record in data.freight_invoices:
        freight[record.order_id].append(record)
    for receipt in data.warehouse_receipts:
        receipts_by_order[receipt.order_id].append(receipt)
        if receipt.return_id:
            receipts_by_return[receipt.return_id].append(receipt)
        if receipt.tracking_id:
            receipts_by_tracking[receipt.tracking_id].append(receipt)

    results: list[OrderResult] = []
    threshold = money(data.threshold) or Decimal("0.00")
    for order in data.orders:
        payment_method = (order.payment_method or "").casefold()
        if payment_method == "cod":
            selected_payments = cods[order.order_id]
            other_payments = settlements[order.order_id]
            conflict = bool(other_payments)
        elif payment_method:
            selected_payments = settlements[order.order_id]
            other_payments = cods[order.order_id]
            conflict = bool(other_payments)
        else:
            selected_payments = settlements[order.order_id] + cods[order.order_id]
            other_payments = []
            conflict = bool(settlements[order.order_id] and cods[order.order_id])

        received = money(sum((money(item.amount) or Decimal("0.00") for item in selected_payments), Decimal("0.00"))) if selected_payments else None
        expected = money(order.expected_amount)
        difference = money(received - expected) if received is not None and expected is not None else None
        tcs = money(sum((money(item.gst_tcs) or Decimal("0.00") for item in selected_payments), Decimal("0.00"))) or Decimal("0.00")
        tds = money(sum((money(item.income_tax_tds) or Decimal("0.00") for item in selected_payments), Decimal("0.00"))) or Decimal("0.00")
        evidence = []
        if order.source_import_id:
            evidence.append({"source_type": "order", "import_id": order.source_import_id, "row_number": order.source_row_number})
        for item in selected_payments + (other_payments if conflict else []):
            evidence.append({"source_type": item.source_type, "import_id": item.source_import_id, "row_number": item.source_row_number, "transaction_id": item.transaction_id})
        findings: list[Finding] = []
        status = "PENDING"

        if conflict:
            findings.append(Finding("PAYMENT_SOURCE_CONFLICT", None, "Both COD remittance and settlement records exist for this order; data was not combined to avoid double counting.", evidence, False))
            status = "UNDER_REVIEW"
        elif expected is not None and received is not None:
            gap = expected - received
            if abs(gap) <= threshold:
                status = "SETTLED"
            elif expected < 0 and received < expected:
                amount = money(abs(gap))
                findings.append(Finding("REFUND_OVERPAID", amount, f"Refund received is {amount} more negative than the expected refund; review the excess refund.", evidence, True))
                status = "REFUND_OVERPAID"
            elif gap > threshold:
                findings.append(Finding("SHORT_PAID", money(gap), f"Expected {expected}; received {received}; short payment is {money(gap)} (above the {threshold} threshold).", evidence, True))
                status = "SHORT_PAID"
            elif gap < -threshold:
                findings.append(Finding("OVERPAID", money(abs(gap)), f"Received amount exceeds expected amount by {money(abs(gap))}; review before classifying as leakage.", evidence, False))
                status = "UNDER_REVIEW"
        elif order.expected_amount is None:
            status = "PENDING"
            findings.append(Finding("MISSING_EXPECTED_AMOUNT", None, "Expected amount is unavailable; no payment discrepancy was classified.", evidence, False))
        elif not selected_payments:
            if order.payment_eligible and order.settlement_due_date and data.as_of > order.settlement_due_date:
                status = "UNPAID_PAST_DUE"
                findings.append(Finding("UNPAID_PAST_DUE", expected, f"No matching payment record exists and the configured due date {order.settlement_due_date} has passed.", evidence, True))
            else:
                status = "PENDING"
                reason = "Payment is not yet due." if order.settlement_due_date and data.as_of <= order.settlement_due_date else "Payment eligibility or a settlement due date is unavailable."
                findings.append(Finding("PAYMENT_PENDING", None, reason + " Missing data is not treated as a confirmed loss.", evidence, False))
        else:
            status = "PENDING"
            findings.append(Finding("MISSING_EXPECTED_AMOUNT", None, "Received records exist, but expected amount is unavailable; no discrepancy was classified.", evidence, False))

        order_freight = freight[order.order_id]
        if order_freight:
            billed_total = Decimal("0.00")
            expected_total = Decimal("0.00")
            freight_evidence = []
            unverified_reason = False
            for invoice in order_freight:
                freight_evidence.append({
                    "source_type": "freight_invoice", "import_id": invoice.source_import_id,
                    "row_number": invoice.source_row_number, "transaction_id": invoice.transaction_id,
                    "tracking_id": invoice.tracking_id,
                })
                rate = _find_rate(invoice, data.rate_cards, data.as_of)
                if rate is None or (rate.percentage_charge and order.order_value is None):
                    unverified_reason = True
                    continue
                billed_total += money(invoice.billed_charge) or Decimal("0.00")
                expected_total += calculate_freight(
                    rate,
                    order_value=order.order_value,
                    is_cod=payment_method == "cod",
                    is_return=(order.return_status or "").casefold() in {"returned", "returned to warehouse", "return to origin", "rto"},
                )
            if unverified_reason:
                findings.append(Finding("FREIGHT_UNVERIFIABLE", None, "At least one invoice lacks an effective rate card or data needed for a percentage charge; no aggregate freight overcharge was asserted.", freight_evidence, False))
                if status in {"PENDING", "SETTLED"}:
                    status = "UNDER_REVIEW"
            else:
                freight_gap = money(billed_total - expected_total) or Decimal("0.00")
                if freight_gap > threshold:
                    findings.append(Finding("FREIGHT_OVERCHARGED", freight_gap, f"Courier billed {money(billed_total)} in total; rate cards calculate {money(expected_total)}; excess is {freight_gap} (above the {threshold} threshold).", freight_evidence, True))
                    if status in {"PENDING", "SETTLED"}:
                        status = "FREIGHT_OVERCHARGED"

        if (order.return_status or "").casefold() in {"returned", "returned to warehouse", "return to origin", "rto", "delivered back to courier"}:
            receipt_matches = list(receipts_by_order[order.order_id])
            if order.return_id:
                receipt_matches.extend(receipts_by_return[order.return_id])
            if order.tracking_id:
                receipt_matches.extend(receipts_by_tracking[order.tracking_id])
            receipt_matches = list({id(receipt): receipt for receipt in receipt_matches}.values())
            if order.return_deadline and order.return_deadline < data.as_of and not receipt_matches:
                return_evidence = evidence + [{"source_type": "return_status", "status": order.return_status, "deadline": str(order.return_deadline)}]
                findings.append(Finding("RETURN_NOT_RECEIVED", None, f"Order is marked returned, the return deadline {order.return_deadline} has passed, and no matching warehouse scan exists.", return_evidence, True))
                if status in {"PENDING", "SETTLED"}:
                    status = "RETURN_NOT_RECEIVED"
            elif order.return_deadline is None:
                findings.append(Finding("RETURN_PENDING", None, "Return status exists but no configured return deadline is available; warehouse receipt is not assumed.", evidence, False))

        reason_text = " ".join(finding.explanation for finding in findings) or "No discrepancy found under the supplied rules."
        tax_text = f" GST TCS: {tcs}; income-tax TDS: {tds}." if (tcs or tds) else " GST TCS and income-tax TDS: 0.00."
        results.append(OrderResult(order.order_id, status, expected, received, difference, tcs, tds, findings, reason_text + tax_text, evidence, order.partner_id))

    unmatched_order_ids = (set(settlements) | set(cods) | set(freight)) - set(orders_by_id)
    for order_id in sorted(unmatched_order_ids):
        payments = settlements[order_id] + cods[order_id]
        evidence = [{
            "source_type": item.source_type, "import_id": item.source_import_id,
            "row_number": item.source_row_number, "transaction_id": item.transaction_id,
        } for item in payments]
        evidence.extend({
            "source_type": "freight_invoice", "import_id": item.source_import_id,
            "row_number": item.source_row_number, "transaction_id": item.transaction_id,
        } for item in freight[order_id])
        findings = [Finding(
            "UNMATCHED_SOURCE_RECORD", None,
            "Partner transaction records reference an order that is absent from the supplied order data; no financial loss was classified.",
            evidence, False,
        )]
        results.append(OrderResult(
            order_id, "PENDING", None, None, None, Decimal("0.00"), Decimal("0.00"), findings,
            findings[0].explanation, evidence, None,
        ))
    return results
