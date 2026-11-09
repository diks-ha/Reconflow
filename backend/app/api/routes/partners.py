from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.session import get_db
from app.models.partner import Partner
from app.models.user import User
from app.schemas.imports import PartnerCreate, PartnerResponse
from app.imports.service import create_partner

router = APIRouter(prefix="/partners", tags=["partners"])


@router.get("", response_model=list[PartnerResponse])
def get_partners(
    _: User = Depends(require_roles("FINANCE_EXECUTIVE", "FINANCE_COFOUNDER")),
    db: Session = Depends(get_db),
) -> list[Partner]:
    return list(db.scalars(select(Partner).order_by(Partner.name)))


@router.post("", response_model=PartnerResponse, status_code=status.HTTP_201_CREATED)
def post_partner(
    payload: PartnerCreate,
    _: User = Depends(require_roles("FINANCE_COFOUNDER")),
    db: Session = Depends(get_db),
) -> Partner:
    try:
        return create_partner(db, payload.name, payload.partner_type.value)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

