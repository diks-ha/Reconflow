from uuid import UUID
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.session import get_db
from app.imports.constants import ReportType
from app.imports.file_service import ImportFileError
from app.imports.service import (
    DuplicateImportError,
    apply_mapping_template,
    save_import,
    validate_import,
)
from app.models.import_record import ImportRecord
from app.models.partner import Partner
from app.models.user import User
from app.schemas.imports import (
    ApplyTemplateRequest,
    ApproveMappingRequest,
    ImportResponse,
    PreviewResponse,
)
from app.imports.service import approve_mapping
from app.reconciliation.imports import ImportProcessingError, process_validated_import

router = APIRouter(prefix="/imports", tags=["imports"])
finance_user = require_roles("FINANCE_EXECUTIVE", "FINANCE_COFOUNDER")
_SENSITIVE_PREVIEW_COLUMNS = (
    "email", "phone", "telephone", "mobile", "address", "fullname", "firstname", "lastname",
    "shippingname", "billingname", "contactname", "customer", "buyer", "recipient",
    "consignee", "pincode", "postalcode", "aadhaar", "aadhar", "pan", "bankaccount",
    "accountnumber", "creditcard", "cardnumber", "cvv",
)


def _mask_preview_value(header: str, value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", header.casefold())
    if normalized == "name" or any(token in normalized for token in _SENSITIVE_PREVIEW_COLUMNS):
        return "[REDACTED]" if value else value
    return value


@router.post("/upload", response_model=ImportResponse, status_code=status.HTTP_201_CREATED)
def upload_import(
    file: UploadFile = File(...),
    partner_id: UUID = Form(...),
    report_type: ReportType = Form(...),
    user: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> ImportRecord:
    if db.get(Partner, partner_id) is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    try:
        return save_import(db, file, file.filename or "upload", partner_id, report_type.value, user)
    except DuplicateImportError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "existing_import_id": str(exc.import_id)}) from None
    except ImportFileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("", response_model=list[ImportResponse])
def list_imports(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    partner_id: UUID | None = None,
    report_type: ReportType | None = None,
    import_status: str | None = Query(default=None, alias="status"),
    _: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> list[ImportRecord]:
    query = select(ImportRecord)
    if partner_id:
        query = query.where(ImportRecord.partner_id == partner_id)
    if report_type:
        query = query.where(ImportRecord.report_type == report_type.value)
    if import_status:
        query = query.where(ImportRecord.status == import_status.upper())
    return list(db.scalars(query.order_by(ImportRecord.created_at.desc()).offset(offset).limit(limit)))


@router.get("/{import_id}", response_model=ImportResponse)
def get_import(import_id: UUID, _: User = Depends(finance_user), db: Session = Depends(get_db)) -> ImportRecord:
    record = db.get(ImportRecord, import_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return record


@router.get("/{import_id}/preview", response_model=PreviewResponse)
def preview_import(import_id: UUID, _: User = Depends(finance_user), db: Session = Depends(get_db)) -> PreviewResponse:
    record = db.get(ImportRecord, import_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Import not found")
    masked_rows = [
        {header: _mask_preview_value(header, value) for header, value in row.items()}
        for row in record.preview_rows
    ]
    return PreviewResponse(import_id=record.id, headers=record.headers, rows=masked_rows)


@router.post("/{import_id}/approve", status_code=status.HTTP_201_CREATED)
def approve_import_mapping(
    import_id: UUID,
    payload: ApproveMappingRequest,
    user: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> dict:
    record = db.get(ImportRecord, import_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Import not found")
    try:
        version = approve_mapping(db, record, user, payload.template_name, [item.model_dump() for item in payload.mappings])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"mapping_version_id": str(version.id), "template_id": str(version.template_id), "version_number": version.version_number, "status": record.status}


@router.post("/{import_id}/apply-template")
def apply_template(
    import_id: UUID,
    payload: ApplyTemplateRequest,
    _: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> dict:
    record = db.get(ImportRecord, import_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Import not found")
    try:
        version = apply_mapping_template(db, record, payload.mapping_version_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"mapping_version_id": str(version.id), "status": record.status}


@router.post("/{import_id}/validate")
def validate_import_data(import_id: UUID, _: User = Depends(finance_user), db: Session = Depends(get_db)) -> dict:
    record = db.get(ImportRecord, import_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Import not found")
    try:
        report = validate_import(db, record)
    except ImportFileError as exc:
        record.status = "FAILED"
        record.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"import_id": str(record.id), "status": record.status, "validation": report}


@router.post("/{import_id}/process")
def process_import_data(import_id: UUID, _: User = Depends(finance_user), db: Session = Depends(get_db)) -> dict:
    try:
        return process_validated_import(db, import_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ImportProcessingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Duplicate financial transaction or source row detected") from None

