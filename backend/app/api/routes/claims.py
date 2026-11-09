import csv
from io import StringIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.session import get_db
from app.models.finance import AuditLog, Claim, ClaimEvidence, ClaimNote, ReconciliationResult
from app.models.import_record import ImportRecord
from app.models.partner import Partner
from app.models.user import User
from app.schemas.claims import ClaimNoteCreate, ClaimStatusUpdate

router = APIRouter(prefix="/claims", tags=["claims"])
finance_user = require_roles("FINANCE_EXECUTIVE", "FINANCE_COFOUNDER")


def _claim_query(db: Session, claim_id: UUID) -> Claim:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


def _serialize_many(claims: list[Claim], db: Session) -> list[dict]:
    """Serialize a claims page using bounded set queries instead of per-claim queries."""
    if not claims:
        return []
    claim_ids = [claim.id for claim in claims]
    result_ids = {claim.reconciliation_result_id for claim in claims}
    partner_ids = {claim.partner_id for claim in claims if claim.partner_id}
    reviewer_ids = {claim.assigned_reviewer_id for claim in claims if claim.assigned_reviewer_id}
    partners = {item.id: item for item in db.scalars(select(Partner).where(Partner.id.in_(partner_ids)))} if partner_ids else {}
    results = {item.id: item for item in db.scalars(select(ReconciliationResult).where(ReconciliationResult.id.in_(result_ids)))}
    reviewers = {item.id: item for item in db.scalars(select(User).where(User.id.in_(reviewer_ids)))} if reviewer_ids else {}
    notes_by_claim: dict[UUID, list[ClaimNote]] = {}
    for item in db.scalars(select(ClaimNote).where(ClaimNote.claim_id.in_(claim_ids)).order_by(ClaimNote.created_at)):
        notes_by_claim.setdefault(item.claim_id, []).append(item)
    evidence_by_claim: dict[UUID, list[ClaimEvidence]] = {}
    evidence_rows = list(db.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id.in_(claim_ids)).order_by(ClaimEvidence.created_at)))
    for item in evidence_rows:
        evidence_by_claim.setdefault(item.claim_id, []).append(item)
    import_ids = {item.source_import_id for item in evidence_rows if item.source_import_id}
    imports = {item.id: item for item in db.scalars(select(ImportRecord).where(ImportRecord.id.in_(import_ids)))} if import_ids else {}
    output = []
    for claim in claims:
        partner = partners.get(claim.partner_id)
        result = results.get(claim.reconciliation_result_id)
        reviewer = reviewers.get(claim.assigned_reviewer_id)
        evidence = [{
            "source_import_id": str(item.source_import_id) if item.source_import_id else None,
            "source_filename": imports[item.source_import_id].original_filename if item.source_import_id in imports else None,
            "transaction_id": item.transaction_id,
            "source_row_number": item.source_row_number,
            "details": item.evidence_json,
        } for item in evidence_by_claim.get(claim.id, [])]
        output.append({
            "id": str(claim.id), "partner_id": str(claim.partner_id) if claim.partner_id else None,
            "partner": partner.name if partner else "Unassigned", "order_id": claim.order_id,
            "category": claim.category, "expected_amount": str(result.expected_amount) if result and result.expected_amount is not None else None,
            "received_amount": str(result.received_amount) if result and result.received_amount is not None else None,
            "discrepancy_amount": str(claim.amount) if claim.amount is not None else None,
            "recovered_amount": str(claim.recovered_amount),
            "status": claim.status, "reason": result.explanation if result else "",
            "created_at": claim.created_at, "updated_at": claim.updated_at,
            "assigned_reviewer": {"id": str(reviewer.id), "name": reviewer.full_name} if reviewer else None,
            "evidence": evidence,
            "notes": [{"id": str(note.id), "user_id": str(note.user_id), "note": note.note, "created_at": note.created_at}
                      for note in notes_by_claim.get(claim.id, [])],
        })
    return output


def _serialize(claim: Claim, db: Session) -> dict:
    return _serialize_many([claim], db)[0]


@router.get("")
def list_claims(
    partner_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    search: str | None = None,
    sort_by: str = Query(default="age", pattern="^(age|amount)$"),
    descending: bool = True,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(Claim)
    if partner_id:
        query = query.where(Claim.partner_id == partner_id)
    if status_filter:
        query = query.where(Claim.status == status_filter.upper())
    if category:
        query = query.where(Claim.category == category.upper())
    if search:
        term = f"%{search.strip()}%"
        query = query.where(or_(Claim.order_id.ilike(term), Claim.category.ilike(term)))
    ordering = Claim.amount if sort_by == "amount" else Claim.created_at
    query = query.order_by(ordering.desc() if descending else ordering.asc()).offset(offset).limit(limit)
    return _serialize_many(list(db.scalars(query)), db)


@router.get("/export")
def export_claim_evidence(
    partner_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    _: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> Response:
    query = select(Claim)
    if partner_id:
        query = query.where(Claim.partner_id == partner_id)
    if status_filter:
        query = query.where(Claim.status == status_filter.upper())
    if category:
        query = query.where(Claim.category == category.upper())
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["claim_id", "order_id", "partner", "category", "status", "amount", "recovered_amount", "reason", "source_file", "source_row", "transaction_id"])
    claims = list(db.scalars(query.order_by(Claim.created_at.desc())))
    details = {item["id"]: item for item in _serialize_many(claims, db)}
    for claim in claims:
        detail = details[str(claim.id)]
        rows = detail["evidence"] or [{}]
        for evidence in rows:
            writer.writerow([claim.id, claim.order_id, detail["partner"], claim.category, claim.status,
                             claim.amount, claim.recovered_amount, detail["reason"],
                             evidence.get("source_filename") or "", evidence.get("source_row_number") or "",
                             evidence.get("transaction_id") or ""])
    safe_output = StringIO()
    safe_writer = csv.writer(safe_output)
    for row in csv.reader(StringIO(output.getvalue())):
        safe_writer.writerow([_safe_cell(value) for value in row])
    return Response(content=safe_output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=reconflow-claim-evidence.csv"})


@router.get("/{claim_id}")
def get_claim(claim_id: UUID, _: User = Depends(finance_user), db: Session = Depends(get_db)) -> dict:
    return _serialize(_claim_query(db, claim_id), db)


@router.patch("/{claim_id}/status")
def update_claim_status(
    claim_id: UUID,
    payload: ClaimStatusUpdate,
    user: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> dict:
    claim = _claim_query(db, claim_id)
    before = {"status": claim.status, "recovered_amount": str(claim.recovered_amount),
              "assigned_reviewer_id": str(claim.assigned_reviewer_id) if claim.assigned_reviewer_id else None}
    recovered = payload.recovered_amount if payload.recovered_amount is not None else claim.recovered_amount
    if not recovered.is_finite() or (claim.amount is not None and recovered > claim.amount):
        raise HTTPException(status_code=422, detail="Recovered amount must be finite and cannot exceed the claim amount")
    if payload.assigned_reviewer_id:
        reviewer = db.get(User, payload.assigned_reviewer_id)
        role_names = {association.role.name for association in reviewer.roles} if reviewer is not None else set()
        if reviewer is None or not reviewer.is_active or not role_names.intersection({"FINANCE_EXECUTIVE", "FINANCE_COFOUNDER"}):
            raise HTTPException(status_code=422, detail="Assigned reviewer must be an active finance user")
    claim.status = payload.status
    claim.recovered_amount = recovered
    if payload.assigned_reviewer_id is not None:
        claim.assigned_reviewer_id = payload.assigned_reviewer_id
    after = {"status": claim.status, "recovered_amount": str(claim.recovered_amount),
             "assigned_reviewer_id": str(claim.assigned_reviewer_id) if claim.assigned_reviewer_id else None}
    db.add(AuditLog(user_id=user.id, action="CLAIM_UPDATED", entity_type="claim", entity_id=str(claim.id), before_json=before, after_json=after))
    db.commit()
    db.refresh(claim)
    return _serialize(claim, db)


@router.post("/{claim_id}/notes", status_code=201)
def add_claim_note(
    claim_id: UUID,
    payload: ClaimNoteCreate,
    user: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> dict:
    claim = _claim_query(db, claim_id)
    note = ClaimNote(claim_id=claim.id, user_id=user.id, note=payload.note)
    db.add(note)
    db.flush()
    db.add(AuditLog(user_id=user.id, action="CLAIM_NOTE_ADDED", entity_type="claim", entity_id=str(claim.id), after_json={"note_id": str(note.id)}))
    db.commit()
    db.refresh(note)
    return {"id": str(note.id), "claim_id": str(note.claim_id), "user_id": str(note.user_id), "note": note.note, "created_at": note.created_at}


def _safe_cell(value) -> str:
    text = str(value if value is not None else "")
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text
