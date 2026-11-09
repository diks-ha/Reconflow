from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, case, cast, func, literal, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.session import get_db
from app.models.finance import Claim
from app.models.partner import Partner
from app.models.user import User

router = APIRouter(prefix="/reports", tags=["reports"])
OPEN_STATUSES = {"OPEN", "UNDER_REVIEW", "SUBMITTED"}


@router.get("/money-at-risk")
def money_at_risk(
    as_of: date = Query(default_factory=date.today),
    partner_id: UUID | None = None,
    _: User = Depends(require_roles("FINANCE_EXECUTIVE", "FINANCE_COFOUNDER")),
    db: Session = Depends(get_db),
) -> dict:
    query = select(Claim)
    if partner_id:
        query = query.where(Claim.partner_id == partner_id)
    zero = Decimal("0.00")
    amount = func.coalesce(Claim.amount, zero)
    recovered = func.coalesce(Claim.recovered_amount, zero)
    outstanding = case((amount > recovered, amount - recovered), else_=zero)
    is_open = Claim.status.in_(OPEN_STATUSES)
    # Reuse the endpoint's optional partner scope in each aggregate statement.
    totals_statement = select(
        func.coalesce(func.sum(case((is_open, outstanding), else_=zero)), zero),
        func.coalesce(func.sum(recovered), zero),
        func.coalesce(func.sum(amount), zero),
    )
    if partner_id:
        totals_statement = totals_statement.where(Claim.partner_id == partner_id)
    total_values = db.execute(totals_statement).one()
    totals = {"amount_at_risk": total_values[0], "recovered_amount": total_values[1], "claimed_amount": total_values[2]}

    status_statement = select(Claim.status, func.count(Claim.id), func.coalesce(func.sum(amount), zero))
    if partner_id:
        status_statement = status_statement.where(Claim.partner_id == partner_id)
    status_rows = db.execute(status_statement.group_by(Claim.status)).all()
    by_status = {status: {"claim_count": count, "amount": value} for status, count, value in status_rows}

    partner_statement = select(
        func.coalesce(Partner.name, "Unassigned"), func.count(Claim.id),
        func.coalesce(func.sum(case((is_open, outstanding), else_=zero)), zero),
        func.coalesce(func.sum(recovered), zero),
    ).select_from(Claim).outerjoin(Partner, Partner.id == Claim.partner_id)
    category_statement = select(
        Claim.category, func.count(Claim.id),
        func.coalesce(func.sum(case((is_open, outstanding), else_=zero)), zero),
        func.coalesce(func.sum(recovered), zero),
    )
    if partner_id:
        partner_statement = partner_statement.where(Claim.partner_id == partner_id)
        category_statement = category_statement.where(Claim.partner_id == partner_id)
    partner_rows = db.execute(partner_statement.group_by(Partner.name)).all()
    category_rows = db.execute(category_statement.group_by(Claim.category)).all()
    by_partner = {name: {"claim_count": count, "amount_at_risk": risk, "recovered_amount": recovery}
                  for name, count, risk, recovery in partner_rows}
    by_category = {category: {"claim_count": count, "amount_at_risk": risk, "recovered_amount": recovery}
                   for category, count, risk, recovery in category_rows}

    by_age = {key: {"claim_count": 0, "amount": Decimal("0.00")} for key in ("0-7", "8-15", "16-30", "over-30")}
    if db.bind.dialect.name == "sqlite":
        age_days = func.julianday(as_of.isoformat()) - func.julianday(func.date(Claim.created_at))
    else:
        age_days = literal(as_of, type_=Date) - cast(Claim.created_at, Date)
    age_days = case((age_days < 0, 0), else_=age_days)
    age_bucket = case(
        (age_days <= 7, "0-7"), (age_days <= 15, "8-15"),
        (age_days <= 30, "16-30"), else_="over-30",
    )
    age_statement = select(age_bucket, func.count(Claim.id), func.coalesce(func.sum(outstanding), zero)).where(is_open)
    if partner_id:
        age_statement = age_statement.where(Claim.partner_id == partner_id)
    for bucket, count, value in db.execute(age_statement.group_by(age_bucket)):
        by_age[bucket] = {"claim_count": count, "amount": value}
    return {
        **{key: str(value) for key, value in totals.items()},
        "claims_by_status": {key: {"claim_count": value["claim_count"], "amount": str(value["amount"])} for key, value in by_status.items()},
        "open_claims": {"claim_count": sum(v["claim_count"] for k, v in by_status.items() if k in OPEN_STATUSES),
                        "amount": str(sum((v["amount"] for k, v in by_status.items() if k in OPEN_STATUSES), Decimal("0.00")))},
        "resolved_claims": {"claim_count": by_status.get("RESOLVED", {}).get("claim_count", 0),
                            "amount": str(by_status.get("RESOLVED", {}).get("amount", Decimal("0.00")))},
        "by_partner": [{"partner": key, **{k: str(v) if isinstance(v, Decimal) else v for k, v in value.items()}} for key, value in sorted(by_partner.items())],
        "by_discrepancy_type": [{"category": key, **{k: str(v) if isinstance(v, Decimal) else v for k, v in value.items()}} for key, value in sorted(by_category.items())],
        "by_age_bucket": {key: {"claim_count": value["claim_count"], "amount_at_risk": str(value["amount"])} for key, value in by_age.items()},
        "as_of": as_of.isoformat(),
    }
