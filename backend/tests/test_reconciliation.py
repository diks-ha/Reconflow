from datetime import date
from decimal import Decimal as D

import pytest

from app.reconciliation.engine import (
    DEFAULT_THRESHOLD, FreightInput, OrderInput, PaymentInput, RateInput,
    ReconciliationInput, WarehouseReceiptInput, reconcile,
)
from app.models.finance import Claim, ReconciliationResult
from app.models.user import User
from app.reconciliation.service import execute_and_persist

AS_OF = date(2026, 11, 8)


def test_client_order_examples_are_deterministic():
    results = reconcile(ReconciliationInput(orders=[
        OrderInput("ORD-W-204118", D("1409.00"), payment_method="COD", order_value=D("1499"), delivery_status="Delivered"),
        OrderInput("ORD-M-88120", D("899.00"), payment_method="Prepaid", order_value=D("1199")),
        OrderInput("ORD-W-204377", D("-96.00"), payment_method="Prepaid", order_value=D("2398")),
    ], cod_remittances=[PaymentInput("ORD-W-204118", D("0.00"), source_type="cod_remittance")], settlements=[
        PaymentInput("ORD-M-88120", D("862.00"), transaction_id="SET-88120", gst_tcs=D("2.00"), income_tax_tds=D("1.00")),
        PaymentInput("ORD-W-204377", D("-142.00"), transaction_id="REF-204377"),
    ], as_of=AS_OF))
    by_id = {result.order_id: result for result in results}
    assert by_id["ORD-W-204118"].status == "SHORT_PAID"
    assert by_id["ORD-W-204118"].difference == D("-1409.00")
    assert by_id["ORD-M-88120"].status == "SHORT_PAID"
    assert by_id["ORD-M-88120"].difference == D("-37.00")
    assert by_id["ORD-M-88120"].gst_tcs == D("2.00")
    assert by_id["ORD-M-88120"].income_tax_tds == D("1.00")
    assert "TCS" in by_id["ORD-M-88120"].explanation
    assert by_id["ORD-W-204377"].status == "REFUND_OVERPAID"
    assert by_id["ORD-W-204377"].findings[0].amount == D("46.00")


def test_partial_settlements_are_summed_and_taxes_remain_separate():
    result = reconcile(ReconciliationInput(orders=[OrderInput("O-1", D("1000.00"), "Prepaid")], settlements=[
        PaymentInput("O-1", D("400.00"), transaction_id="T-1", partner_id="P", gst_tcs=D("3.00")),
        PaymentInput("O-1", D("600.00"), transaction_id="T-2", partner_id="P", income_tax_tds=D("2.00")),
    ]))[0]
    assert result.status == "SETTLED"
    assert result.received_amount == D("1000.00")
    assert result.gst_tcs == D("3.00")
    assert result.income_tax_tds == D("2.00")


def test_cod_past_due_requires_explicit_eligibility_and_due_date():
    order = OrderInput("COD-1", D("500"), "COD", delivery_status="Delivered", payment_eligible=True,
                       settlement_due_date=date(2026, 11, 1))
    result = reconcile(ReconciliationInput(orders=[order], as_of=AS_OF))[0]
    assert result.status == "UNPAID_PAST_DUE"
    assert result.findings[0].confirmed
    pending = reconcile(ReconciliationInput(orders=[OrderInput("COD-2", D("500"), "COD")], as_of=AS_OF))[0]
    assert pending.status == "PENDING"
    assert not pending.findings[0].confirmed


def test_exact_threshold_is_not_flagged_but_above_threshold_is():
    results = reconcile(ReconciliationInput(
        orders=[OrderInput("O-10", D("100"), "Prepaid"), OrderInput("O-11", D("100"), "Prepaid")],
        settlements=[PaymentInput("O-10", D("90")), PaymentInput("O-11", D("89.99"))],
    ))
    assert results[0].status == "SETTLED"
    assert results[1].status == "SHORT_PAID"
    assert DEFAULT_THRESHOLD == D("10.00")


def test_freight_overcharge_uses_effective_rate_card_and_decimal_math():
    rate = RateInput("Website", "Courier A", D("0"), D("1"), D("50"), cod_fee=D("10"),
                     fixed_charge=D("2"), percentage_charge=D("1"), effective_from=date(2026, 1, 1))
    result = reconcile(ReconciliationInput(
        orders=[OrderInput("F-1", D("100"), "COD", order_value=D("1000"), channel="Website")],
        freight_invoices=[FreightInput("F-1", D("85"), "Website", "Courier A", D("0.5"), transaction_id="INV-1")],
        rate_cards=[rate], as_of=AS_OF,
    ))[0]
    # expected freight = 50 + 10 COD + 2 fixed + 1% * 1000 = 72
    finding = next(item for item in result.findings if item.category == "FREIGHT_OVERCHARGED")
    assert finding.amount == D("13.00")


def test_freight_missing_rate_card_is_not_a_confirmed_loss():
    result = reconcile(ReconciliationInput(
        orders=[OrderInput("F-2", D("100"), "Prepaid", channel="Website")],
        freight_invoices=[FreightInput("F-2", D("90"), "Website", "Unknown Courier", D("1"))],
    ))[0]
    assert result.status == "UNDER_REVIEW"
    assert any(item.category == "FREIGHT_UNVERIFIABLE" and not item.confirmed for item in result.findings)


def test_return_not_received_requires_expired_deadline_and_no_scan():
    order = OrderInput("R-1", D("0"), "Prepaid", return_status="Returned to warehouse",
                       return_id="RET-1", tracking_id="AWB-1", return_deadline=date(2026, 11, 1))
    flagged = reconcile(ReconciliationInput(orders=[order], as_of=AS_OF))[0]
    assert any(f.category == "RETURN_NOT_RECEIVED" and f.confirmed for f in flagged.findings)
    received = reconcile(ReconciliationInput(orders=[order], warehouse_receipts=[
        WarehouseReceiptInput("R-1", date(2026, 11, 3), return_id="RET-1", tracking_id="AWB-1")
    ], as_of=AS_OF))[0]
    assert not any(f.category == "RETURN_NOT_RECEIVED" for f in received.findings)


def test_duplicate_transactions_and_duplicate_orders_are_rejected():
    with pytest.raises(ValueError, match="Duplicate transaction"):
        reconcile(ReconciliationInput(orders=[OrderInput("O-1", D("20"))], settlements=[
            PaymentInput("O-1", D("10"), "DUP", "P"), PaymentInput("O-1", D("10"), "DUP", "P")
        ]))
    with pytest.raises(ValueError, match="Duplicate order"):
        reconcile(ReconciliationInput(orders=[OrderInput("O-1", D("20")), OrderInput("O-1", D("20"))]))


def test_results_and_claims_persist_transactionally_without_duplicate_claims(db):
    user = db.query(User).filter_by(email="exec@example.com").one()
    inputs = ReconciliationInput(
        orders=[OrderInput("PERSIST-1", D("100"), "Prepaid")],
        settlements=[PaymentInput("PERSIST-1", D("50"), transaction_id="P-1", partner_id="P")],
    )
    run, created = execute_and_persist(db, user, inputs)
    assert run.summary["statuses"] == {"SHORT_PAID": 1}
    assert created == 1
    assert db.query(ReconciliationResult).filter_by(run_id=run.id).one().difference == D("-50.00")
    second_run, created_again = execute_and_persist(db, user, inputs)
    assert second_run.id != run.id
    assert created_again == 0
    assert db.query(Claim).filter_by(order_id="PERSIST-1", category="SHORT_PAID").count() == 1

