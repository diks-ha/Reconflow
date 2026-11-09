import csv
from datetime import date, timedelta
from decimal import Decimal as D
from io import StringIO

from app.api.routes.claims import add_claim_note, export_claim_evidence, update_claim_status
from app.api.routes.audit import list_audit_logs
from app.api.routes.rate_cards import activate_rate_card, create_rate_card, deactivate_rate_card, rate_card_history, revise_rate_card
from app.api.routes.reports import money_at_risk
from app.api.routes.returns import list_returns
from app.models.finance import (
    AuditLog, Claim, ClaimEvidence, RateCard, ReturnRecord, WarehouseReceipt,
)
from app.models.import_record import ImportRecord
from app.models.partner import Partner
from app.models.user import User
from app.reconciliation.engine import OrderInput, PaymentInput, ReconciliationInput
from app.reconciliation.service import execute_and_persist
from app.schemas.claims import ClaimNoteCreate, ClaimStatusUpdate
from app.schemas.rate_cards import RateCardCreate


def _partner(db, name="Sample Courier"):
    row = Partner(name=name, partner_type="COURIER")
    db.add(row)
    db.commit()
    return row


def _rate_payload(fee="55.00"):
    return RateCardCreate(
        channel="Marketplace 1", courier_partner="Sample Courier", min_weight=D("0"), max_weight=D("1"),
        forward_fee=D(fee), return_fee=D("60"), cod_fee=D("15"), fixed_charge=D("2"),
        percentage_charge=D("0"), effective_from=date.today() - timedelta(days=2), source_note="Illustrative test rate",
    )


def test_rate_card_revision_and_activation_are_versioned(db):
    founder = db.query(User).filter_by(email="founder@example.com").one()
    card = create_rate_card(_rate_payload(), founder, db)
    assert card.version_number == 1
    revised = revise_rate_card(card.id, _rate_payload("58"), founder, db)
    assert revised.version_number == 2
    assert revised.supersedes_id == card.id
    history = rate_card_history(revised.id, founder, db)
    assert len(history) >= 2
    deactivated = deactivate_rate_card(revised.id, founder, db)
    assert deactivated.is_active is False
    activated = activate_rate_card(revised.id, founder, db)
    assert activated.is_active is True


def test_returns_tracker_uses_warehouse_scan_evidence(db):
    founder = db.query(User).filter_by(email="founder@example.com").one()
    partner = _partner(db)
    source = ImportRecord(
        uploaded_by=founder.id, partner_id=partner.id, report_type="orders", original_filename="returns.csv",
        storage_key="illustrative://returns", file_hash="a" * 64, file_size=0, file_format="csv",
        status="PROCESSED", headers=[], preview_rows=[], row_count=1,
    )
    db.add(source)
    db.flush()
    record = ReturnRecord(
        partner_id=partner.id, order_id="RET-100", return_id="R-100", tracking_id="AWB-100",
        courier_partner="Sample Courier", return_status="Returned to warehouse", deadline=date.today() - timedelta(days=3),
        source_import_id=source.id, source_row_number=2, raw_source={"sample": True},
    )
    no_deadline = ReturnRecord(
        partner_id=partner.id, order_id="RET-NO-DEADLINE", return_id="R-NO-DATE",
        return_status="Return initiated", deadline=None, source_import_id=source.id,
        source_row_number=4, raw_source={"sample": True},
    )
    db.add_all([record, no_deadline])
    db.commit()
    overdue = list_returns(partner_id=partner.id, courier_partner="Sample", overdue=True, as_of=date.today(), offset=0, limit=1, _=founder, db=db)
    assert len(overdue) == 1 and overdue[0]["order_id"] == "RET-100"
    assert overdue[0]["days_overdue"] == 3
    db.add(WarehouseReceipt(order_id="RET-100", return_id="R-100", tracking_id="AWB-100", received_at=date.today(), source_import_id=source.id, source_row_number=3, raw_source={"scan": "verified"}))
    db.commit()
    current = list_returns(partner_id=partner.id, overdue=False, as_of=date.today(), offset=0, limit=20, _=founder, db=db)
    received = next(item for item in current if item["order_id"] == "RET-100")
    assert received["warehouse_scan_status"] == "RECEIVED"
    assert received["evidence"][0]["source_row_number"] == 3


def test_claim_lifecycle_evidence_csv_audit_and_database_exposure(db):
    executive = db.query(User).filter_by(email="exec@example.com").one()
    partner = _partner(db, "Marketplace Sample")
    source = ImportRecord(
        uploaded_by=executive.id, partner_id=partner.id, report_type="marketplace_settlement", original_filename="settlement.csv",
        storage_key="illustrative://settlement", file_hash="b" * 64, file_size=0, file_format="csv",
        status="PROCESSED", headers=[], preview_rows=[], row_count=1,
    )
    db.add(source)
    db.commit()
    run, created = execute_and_persist(db, executive, ReconciliationInput(
        orders=[OrderInput("CLAIM-1", D("200"), "Prepaid", partner_id=str(partner.id))],
        settlements=[PaymentInput("CLAIM-1", D("150"), transaction_id="TX-CLAIM-1", partner_id=str(partner.id),
                                  source_import_id=str(source.id), source_row_number=2)],
    ))
    assert created == 1
    claim = db.query(Claim).filter_by(order_id="CLAIM-1").one()
    assert db.query(ClaimEvidence).filter_by(claim_id=claim.id).count() == 1
    assert claim.partner_id == partner.id

    note = add_claim_note(claim.id, ClaimNoteCreate(note=" Partner contacted; awaiting response "), executive, db)
    assert note["note"] == "Partner contacted; awaiting response"
    founder = db.query(User).filter_by(email="founder@example.com").one()
    updated = update_claim_status(claim.id, ClaimStatusUpdate(status="UNDER_REVIEW", recovered_amount=D("20"), assigned_reviewer_id=founder.id), executive, db)
    assert updated["recovered_amount"] == "20.00"
    assert updated["assigned_reviewer"]["id"] == str(founder.id)
    export = export_claim_evidence(partner_id=partner.id, status_filter="UNDER_REVIEW", category="SHORT_PAID", _=executive, db=db)
    assert "settlement.csv" in export.body.decode()
    assert db.query(AuditLog).filter(AuditLog.entity_id == str(claim.id)).count() == 3
    logs = list_audit_logs(entity_type="claim", entity_id=str(claim.id), action=None, offset=0, limit=20, _=executive, db=db)
    assert {entry["action"] for entry in logs} == {"CLAIM_AUTO_GENERATED", "CLAIM_NOTE_ADDED", "CLAIM_UPDATED"}
    exported_rows = list(csv.reader(StringIO(export.body.decode())))
    assert len(exported_rows[0]) == len(exported_rows[1]) == 11
    assert exported_rows[1][8] == "settlement.csv"

    exposure = money_at_risk(as_of=date.today(), partner_id=partner.id, _=executive, db=db)
    assert exposure["amount_at_risk"] == "30.00"
    assert exposure["recovered_amount"] == "20.00"
    assert exposure["by_partner"][0]["partner"] == "Marketplace Sample"

