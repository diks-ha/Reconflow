from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.finance import AuditLog, Claim, ClaimEvidence, ReconciliationResult, ReconciliationRun
from app.models.user import User
from app.reconciliation.engine import ReconciliationInput, reconcile

CLAIM_CATEGORIES = {"SHORT_PAID", "UNPAID_PAST_DUE", "FREIGHT_OVERCHARGED", "RETURN_NOT_RECEIVED", "REFUND_OVERPAID"}
RESULT_BATCH_SIZE = 1000
CLAIM_BATCH_SIZE = 50


def execute_and_persist(db: Session, user: User, inputs: ReconciliationInput) -> tuple[ReconciliationRun, int]:
    """Calculate then persist results, claims, evidence and audits in batched writes.

    Reconciliation itself builds indexed joins in memory. Results and claim inserts are
    written in bounded batches inside one transaction to avoid one flush/round trip per order.
    """
    results = reconcile(inputs)
    threshold = inputs.threshold.quantize(Decimal("0.01"))
    run = ReconciliationRun(created_by=user.id, threshold=threshold, status="COMPLETED", summary={})
    claims_created = 0
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()

            result_rows: list[dict] = []
            result_ids: dict[str, UUID] = {}
            counts: dict[str, int] = {}
            for result in results:
                result_id = uuid4()
                result_ids[result.order_id] = result_id
                result_partner_id = UUID(result.partner_id) if result.partner_id else None
                result_rows.append({
                    "id": result_id,
                    "run_id": run.id,
                    "partner_id": result_partner_id,
                    "order_id": result.order_id,
                    "status": result.status,
                    "expected_amount": result.expected_amount,
                    "received_amount": result.received_amount,
                    "difference": result.difference,
                    "gst_tcs": result.gst_tcs,
                    "income_tax_tds": result.income_tax_tds,
                    "findings": [{
                        "category": item.category,
                        "amount": str(item.amount) if item.amount is not None else None,
                        "explanation": item.explanation,
                        "evidence": item.evidence,
                        "confirmed": item.confirmed,
                    } for item in result.findings],
                    "evidence": result.evidence,
                    "explanation": result.explanation,
                })
                counts[result.status] = counts.get(result.status, 0) + 1

            for offset in range(0, len(result_rows), RESULT_BATCH_SIZE):
                db.execute(insert(ReconciliationResult), result_rows[offset:offset + RESULT_BATCH_SIZE])

            candidates: list[tuple[dict, list[dict]]] = []
            seen_keys: set[tuple[str, str]] = set()
            for result in results:
                for finding in result.findings:
                    if not finding.confirmed or finding.category not in CLAIM_CATEGORIES:
                        continue
                    key = (result.order_id, finding.category)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    claim_id = uuid4()
                    candidates.append(({
                        "id": claim_id,
                        "reconciliation_result_id": result_ids[result.order_id],
                        "partner_id": UUID(result.partner_id) if result.partner_id else None,
                        "order_id": result.order_id,
                        "category": finding.category,
                        "amount": finding.amount,
                        "status": "OPEN",
                        "recovered_amount": Decimal("0.00"),
                    }, finding.evidence))

            dialect = db.bind.dialect.name
            for offset in range(0, len(candidates), CLAIM_BATCH_SIZE):
                batch = candidates[offset:offset + CLAIM_BATCH_SIZE]
                values = [candidate for candidate, _ in batch]
                if dialect == "postgresql":
                    statement = pg_insert(Claim).values(values).on_conflict_do_nothing(
                        constraint="uq_claim_order_category"
                    ).returning(Claim.id, Claim.order_id, Claim.category)
                    inserted_claims = list(db.execute(statement).mappings())
                elif dialect == "sqlite":
                    statement = sqlite_insert(Claim).values(values).on_conflict_do_nothing(
                        index_elements=["order_id", "category"]
                    ).returning(Claim.id, Claim.order_id, Claim.category)
                    inserted_claims = list(db.execute(statement).mappings())
                else:
                    inserted_claims = []
                    for candidate, _ in batch:
                        existing = db.scalar(select(Claim.id).where(
                            Claim.order_id == candidate["order_id"], Claim.category == candidate["category"]
                        ))
                        if existing is None:
                            db.add(Claim(**candidate))
                            inserted_claims.append(candidate)
                    if inserted_claims:
                        db.flush()

                inserted_keys = {(item["order_id"], item["category"]): item["id"] for item in inserted_claims}
                evidence_rows: list[dict] = []
                audit_rows: list[dict] = []
                for candidate, evidence_items in batch:
                    key = (candidate["order_id"], candidate["category"])
                    claim_id = inserted_keys.get(key)
                    if claim_id is None:
                        continue
                    claims_created += 1
                    for evidence in evidence_items:
                        source_import_id = evidence.get("import_id")
                        try:
                            source_import_id = UUID(source_import_id) if source_import_id else None
                        except (ValueError, TypeError):
                            source_import_id = None
                        evidence_rows.append({
                            "id": uuid4(),
                            "claim_id": claim_id,
                            "source_import_id": source_import_id,
                            "transaction_id": evidence.get("transaction_id"),
                            "source_row_number": evidence.get("row_number") if isinstance(evidence.get("row_number"), int) else None,
                            "evidence_json": evidence,
                        })
                    audit_rows.append({
                        "id": uuid4(),
                        "user_id": user.id,
                        "action": "CLAIM_AUTO_GENERATED",
                        "entity_type": "claim",
                        "entity_id": str(claim_id),
                        "after_json": {
                            "order_id": candidate["order_id"],
                            "category": candidate["category"],
                            "amount": str(candidate["amount"]) if candidate["amount"] is not None else None,
                        },
                    })
                if evidence_rows:
                    # No generated ORM attributes are needed here; using the table insert
                    # avoids one RETURNING round trip per evidence row on SQLite.
                    db.execute(insert(ClaimEvidence.__table__), evidence_rows)
                if audit_rows:
                    db.execute(insert(AuditLog), audit_rows)

            run.summary = {"results_count": len(results), "statuses": counts, "claims_created": claims_created}
            db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(run)
    return run, claims_created
