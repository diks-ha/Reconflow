from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.session import get_db
from app.models.finance import ReturnRecord, WarehouseReceipt
from app.models.user import User

router = APIRouter(prefix="/returns", tags=["returns"])
finance_user = require_roles("FINANCE_EXECUTIVE", "FINANCE_COFOUNDER")


def _serialize_many(records: list[ReturnRecord], db: Session, as_of: date) -> list[dict]:
    """Load warehouse evidence for a page of returns in one indexed query."""
    order_ids = {row.order_id for row in records if row.order_id}
    return_ids = {row.return_id for row in records if row.return_id}
    tracking_ids = {row.tracking_id for row in records if row.tracking_id}
    predicates = []
    if order_ids:
        predicates.append(WarehouseReceipt.order_id.in_(order_ids))
    if return_ids:
        predicates.append(WarehouseReceipt.return_id.in_(return_ids))
    if tracking_ids:
        predicates.append(WarehouseReceipt.tracking_id.in_(tracking_ids))
    receipts = list(db.scalars(select(WarehouseReceipt).where(or_(*predicates)).order_by(WarehouseReceipt.received_at))) if predicates else []
    by_order: dict[str, list[WarehouseReceipt]] = {}
    by_return: dict[str, list[WarehouseReceipt]] = {}
    by_tracking: dict[str, list[WarehouseReceipt]] = {}
    for receipt in receipts:
        if receipt.order_id:
            by_order.setdefault(receipt.order_id, []).append(receipt)
        if receipt.return_id:
            by_return.setdefault(receipt.return_id, []).append(receipt)
        if receipt.tracking_id:
            by_tracking.setdefault(receipt.tracking_id, []).append(receipt)
    output = []
    for record in records:
        combined = [*by_order.get(record.order_id, [])]
        if record.return_id:
            combined.extend(by_return.get(record.return_id, []))
        if record.tracking_id:
            combined.extend(by_tracking.get(record.tracking_id, []))
        matches = list({item.id: item for item in combined}.values())
        received = next((item for item in matches if item.received_at is not None), None)
        overdue = bool(record.deadline and record.deadline < as_of and received is None)
        output.append({
            "id": str(record.id), "partner_id": str(record.partner_id), "order_id": record.order_id,
            "return_id": record.return_id, "tracking_id": record.tracking_id, "return_status": record.return_status,
            "courier_partner": record.courier_partner,
            "initiated_at": record.initiated_at, "expected_warehouse_arrival": record.deadline,
            "actual_warehouse_receipt": received.received_at if received else None,
            "warehouse_scan_status": "RECEIVED" if received else ("OVERDUE" if overdue else "AWAITING_SCAN"),
            "days_overdue": max((as_of - record.deadline).days, 0) if overdue else 0,
            "overdue": overdue,
            "evidence": [{"import_id": str(item.source_import_id), "source_row_number": item.source_row_number,
                          "received_at": item.received_at, "return_id": item.return_id, "tracking_id": item.tracking_id}
                         for item in matches],
        })
    return output


@router.get("")
def list_returns(
    partner_id: UUID | None = None,
    courier_partner: str | None = None,
    return_status: str | None = None,
    overdue: bool | None = None,
    as_of: date = Query(default_factory=date.today),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(ReturnRecord)
    if partner_id:
        query = query.where(ReturnRecord.partner_id == partner_id)
    if courier_partner:
        query = query.where(ReturnRecord.courier_partner.ilike(f"%{courier_partner.strip()}%"))
    if return_status:
        query = query.where(ReturnRecord.return_status.ilike(f"%{return_status.strip()}%"))
    receipt_keys = [WarehouseReceipt.order_id == ReturnRecord.order_id]
    receipt_keys.append(WarehouseReceipt.return_id == ReturnRecord.return_id)
    receipt_keys.append(WarehouseReceipt.tracking_id == ReturnRecord.tracking_id)
    has_received_scan = exists(select(WarehouseReceipt.id).where(
        or_(*receipt_keys), WarehouseReceipt.received_at.is_not(None)
    ))
    if overdue is True:
        query = query.where(ReturnRecord.deadline.is_not(None), ReturnRecord.deadline < as_of, ~has_received_scan)
    elif overdue is False:
        query = query.where(or_(ReturnRecord.deadline.is_(None), ReturnRecord.deadline >= as_of, has_received_scan))
    rows = list(db.scalars(query.order_by(ReturnRecord.deadline, ReturnRecord.order_id).offset(offset).limit(limit)))
    result = _serialize_many(rows, db, as_of)
    return result


@router.get("/{return_id}")
def get_return(return_id: UUID, as_of: date = Query(default_factory=date.today), _: User = Depends(finance_user), db: Session = Depends(get_db)) -> dict:
    record = db.get(ReturnRecord, return_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Return record not found")
    return _serialize_many([record], db, as_of)[0]
