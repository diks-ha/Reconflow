from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.session import get_db
from app.models.finance import ReconciliationResult, ReconciliationRun
from app.models.user import User
from app.reconciliation.engine import (
    FreightInput, OrderInput, PaymentInput, RateInput, ReconciliationInput, WarehouseReceiptInput,
)
from app.reconciliation.service import execute_and_persist
from app.reconciliation.imports import ImportProcessingError, load_reconciliation_inputs
from app.schemas.reconciliation import ReconciliationRunRequest, ReconciliationRunResponse

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])
finance_user = require_roles("FINANCE_EXECUTIVE", "FINANCE_COFOUNDER")


def _plain_values(model) -> dict:
    values = model.model_dump()
    for key, value in values.items():
        if isinstance(value, UUID):
            values[key] = str(value)
    return values


@router.post("/run", response_model=ReconciliationRunResponse, status_code=status.HTTP_201_CREATED)
def run_reconciliation(
    payload: ReconciliationRunRequest,
    user: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> ReconciliationRunResponse:
    if payload.import_ids:
        try:
            inputs = load_reconciliation_inputs(db, payload.import_ids, payload.as_of, payload.threshold)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ImportProcessingError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
    else:
        inputs = ReconciliationInput(
            orders=[OrderInput(**_plain_values(item)) for item in payload.orders],
            settlements=[PaymentInput(**_plain_values(item), source_type="settlement") for item in payload.settlements],
            cod_remittances=[PaymentInput(**_plain_values(item), source_type="cod_remittance") for item in payload.cod_remittances],
            freight_invoices=[FreightInput(**_plain_values(item)) for item in payload.freight_invoices],
            warehouse_receipts=[WarehouseReceiptInput(**_plain_values(item)) for item in payload.warehouse_receipts],
            rate_cards=[RateInput(**_plain_values(item)) for item in payload.rate_cards],
            as_of=payload.as_of,
            threshold=payload.threshold,
        )
    try:
        run, claims_created = execute_and_persist(db, user, inputs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return ReconciliationRunResponse(
        run_id=run.id,
        status=run.status,
        results_count=run.summary["results_count"],
        claims_created=claims_created,
        summary=run.summary,
    )


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, _: User = Depends(finance_user), db: Session = Depends(get_db)) -> dict:
    run = db.get(ReconciliationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Reconciliation run not found")
    return {"id": str(run.id), "status": run.status, "threshold": str(run.threshold), "summary": run.summary, "created_at": run.created_at}


@router.get("/results")
def list_results(
    run_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    result_status: str | None = Query(default=None, alias="status"),
    _: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(ReconciliationResult).where(ReconciliationResult.run_id == run_id)
    if result_status:
        query = query.where(ReconciliationResult.status == result_status.upper())
    rows = db.scalars(query.order_by(ReconciliationResult.order_id).offset(offset).limit(limit))
    return [_serialize_result(row) for row in rows]


@router.get("/results/{result_id}")
def get_result(result_id: UUID, _: User = Depends(finance_user), db: Session = Depends(get_db)) -> dict:
    result = db.get(ReconciliationResult, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Reconciliation result not found")
    return _serialize_result(result)


def _serialize_result(row: ReconciliationResult) -> dict:
    return {
        "id": str(row.id), "run_id": str(row.run_id), "order_id": row.order_id, "status": row.status,
        "expected_amount": str(row.expected_amount) if row.expected_amount is not None else None,
        "received_amount": str(row.received_amount) if row.received_amount is not None else None,
        "difference": str(row.difference) if row.difference is not None else None,
        "gst_tcs": str(row.gst_tcs), "income_tax_tds": str(row.income_tax_tds),
        "findings": row.findings, "evidence": row.evidence, "explanation": row.explanation,
        "created_at": row.created_at,
    }
