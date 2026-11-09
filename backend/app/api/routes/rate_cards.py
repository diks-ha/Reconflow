from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.session import get_db
from app.models.finance import AuditLog, RateCard, RateCardHistory
from app.models.user import User
from app.schemas.rate_cards import RateCardCreate, RateCardResponse

router = APIRouter(prefix="/rate-cards", tags=["rate cards"])


def _snapshot(card: RateCard) -> dict:
    return {
        "channel": card.channel, "courier_partner": card.courier_partner,
        "min_weight": str(card.min_weight), "max_weight": str(card.max_weight) if card.max_weight is not None else None,
        "forward_fee": str(card.forward_fee), "return_fee": str(card.return_fee), "cod_fee": str(card.cod_fee),
        "fixed_charge": str(card.fixed_charge), "percentage_charge": str(card.percentage_charge),
        "effective_from": card.effective_from.isoformat(),
        "effective_to": card.effective_to.isoformat() if card.effective_to else None,
        "is_active": card.is_active, "source_note": card.source_note,
    }


@router.get("", response_model=list[RateCardResponse])
def list_rate_cards(_: User = Depends(require_roles("FINANCE_EXECUTIVE", "FINANCE_COFOUNDER")), db: Session = Depends(get_db)):
    return list(db.scalars(select(RateCard).order_by(RateCard.effective_from.desc())))


@router.post("", response_model=RateCardResponse, status_code=status.HTTP_201_CREATED)
def create_rate_card(
    payload: RateCardCreate,
    user: User = Depends(require_roles("FINANCE_COFOUNDER")),
    db: Session = Depends(get_db),
):
    card = RateCard(**payload.model_dump(), is_active=True, version_number=1, created_by=user.id)
    db.add(card)
    try:
        db.flush()
        db.add(RateCardHistory(rate_card_id=card.id, version_number=1, snapshot=_snapshot(card), changed_by=user.id))
        db.add(AuditLog(user_id=user.id, action="RATE_CARD_CREATED", entity_type="rate_card", entity_id=str(card.id), after_json=_snapshot(card)))
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=422, detail="Rate card violates a database constraint") from None
    db.refresh(card)
    return card


@router.put("/{rate_card_id}", response_model=RateCardResponse)
def revise_rate_card(
    rate_card_id: UUID,
    payload: RateCardCreate,
    user: User = Depends(require_roles("FINANCE_COFOUNDER")),
    db: Session = Depends(get_db),
):
    current = db.get(RateCard, rate_card_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Rate card not found")
    before = _snapshot(current)
    new_version = RateCard(
        **payload.model_dump(), is_active=True, version_number=current.version_number + 1,
        supersedes_id=current.id, created_by=user.id,
    )
    try:
        current.is_active = False
        db.add(new_version)
        db.flush()
        db.add(RateCardHistory(rate_card_id=new_version.id, version_number=new_version.version_number,
                               snapshot=_snapshot(new_version), changed_by=user.id))
        db.add(AuditLog(user_id=user.id, action="RATE_CARD_REVISED", entity_type="rate_card",
                        entity_id=str(new_version.id), before_json=before, after_json=_snapshot(new_version)))
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=422, detail="Rate card revision violates a database constraint") from None
    db.refresh(new_version)
    return new_version


@router.post("/{rate_card_id}/deactivate", response_model=RateCardResponse)
def deactivate_rate_card(
    rate_card_id: UUID,
    user: User = Depends(require_roles("FINANCE_COFOUNDER")),
    db: Session = Depends(get_db),
):
    card = db.get(RateCard, rate_card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Rate card not found")
    if card.is_active:
        before = _snapshot(card)
        card.is_active = False
        next_version = card.version_number + 1
        card.version_number = next_version
        after = _snapshot(card)
        db.add(RateCardHistory(rate_card_id=card.id, version_number=next_version, snapshot=after, changed_by=user.id))
        db.add(AuditLog(user_id=user.id, action="RATE_CARD_DEACTIVATED", entity_type="rate_card", entity_id=str(card.id), before_json=before, after_json=after))
        db.commit()
        db.refresh(card)
    return card


@router.post("/{rate_card_id}/activate", response_model=RateCardResponse)
def activate_rate_card(
    rate_card_id: UUID,
    user: User = Depends(require_roles("FINANCE_COFOUNDER")),
    db: Session = Depends(get_db),
):
    card = db.get(RateCard, rate_card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Rate card not found")
    if not card.is_active:
        before = _snapshot(card)
        card.is_active = True
        card.version_number += 1
        after = _snapshot(card)
        db.add(RateCardHistory(rate_card_id=card.id, version_number=card.version_number, snapshot=after, changed_by=user.id))
        db.add(AuditLog(user_id=user.id, action="RATE_CARD_ACTIVATED", entity_type="rate_card", entity_id=str(card.id), before_json=before, after_json=after))
        db.commit()
        db.refresh(card)
    return card


@router.get("/{rate_card_id}/history")
def rate_card_history(rate_card_id: UUID, _: User = Depends(require_roles("FINANCE_EXECUTIVE", "FINANCE_COFOUNDER")), db: Session = Depends(get_db)) -> list[dict]:
    card = db.get(RateCard, rate_card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Rate card not found")
    related_ids = {card.id}
    cursor = card
    while cursor.supersedes_id:
        related_ids.add(cursor.supersedes_id)
        cursor = db.get(RateCard, cursor.supersedes_id)
    frontier = set(related_ids)
    while frontier:
        children = set(db.scalars(select(RateCard.id).where(RateCard.supersedes_id.in_(frontier)))) - related_ids
        related_ids.update(children)
        frontier = children
    entries = db.scalars(select(RateCardHistory).where(RateCardHistory.rate_card_id.in_(related_ids)).order_by(RateCardHistory.created_at))
    return [{"id": str(item.id), "rate_card_id": str(item.rate_card_id), "version_number": item.version_number,
             "snapshot": item.snapshot, "changed_by": str(item.changed_by), "created_at": item.created_at} for item in entries]
