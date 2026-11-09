from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.session import get_db
from app.models.finance import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
def list_audit_logs(
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(require_roles("FINANCE_COFOUNDER")),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(AuditLog)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)
    rows = db.scalars(query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit))
    return [{"id": str(row.id), "user_id": str(row.user_id) if row.user_id else None, "action": row.action,
             "entity_type": row.entity_type, "entity_id": row.entity_id, "before": row.before_json,
             "after": row.after_json, "created_at": row.created_at} for row in rows]
