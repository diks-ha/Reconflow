from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.mapping import suggest_mappings
from app.api.deps import require_roles
from app.database.session import get_db
from app.imports.service import list_mapping_templates, list_versions, rollback_mapping
from app.models.import_record import ImportRecord
from app.models.mapping import MappingTemplate, MappingVersion
from app.models.user import User
from app.schemas.imports import MappingSuggestionResponse, MappingTemplateResponse, MappingVersionResponse, RollbackMappingRequest

router = APIRouter(prefix="/mappings", tags=["mappings"])
finance_user = require_roles("FINANCE_EXECUTIVE", "FINANCE_COFOUNDER")


class SuggestMappingsRequest(BaseModel):
    import_id: UUID


@router.post("/suggest", response_model=MappingSuggestionResponse)
async def suggest(
    payload: SuggestMappingsRequest,
    _: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> MappingSuggestionResponse:
    record = db.get(ImportRecord, payload.import_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Import not found")
    try:
        mode, message, suggestions = await suggest_mappings(record.headers)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return MappingSuggestionResponse(mode=mode, message=message, suggestions=suggestions)


@router.get("", response_model=list[MappingTemplateResponse])
def get_mappings(
    partner_id: UUID | None = None,
    report_type: str | None = None,
    _: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> list[MappingTemplateResponse]:
    templates = list_mapping_templates(db, partner_id, report_type)
    output = []
    for template in templates:
        latest = db.scalar(
            select(MappingVersion).where(MappingVersion.template_id == template.id).order_by(MappingVersion.version_number.desc()).limit(1)
        )
        output.append(MappingTemplateResponse(
            id=template.id,
            partner_id=template.partner_id,
            report_type=template.report_type,
            name=template.name,
            created_at=template.created_at,
            latest_version=MappingVersionResponse.model_validate(latest) if latest else None,
        ))
    return output


@router.get("/{template_id}/versions", response_model=list[MappingVersionResponse])
def get_mapping_versions(template_id: UUID, _: User = Depends(finance_user), db: Session = Depends(get_db)) -> list[MappingVersion]:
    if db.get(MappingTemplate, template_id) is None:
        raise HTTPException(status_code=404, detail="Mapping template not found")
    return list_versions(db, template_id)


@router.post("/{template_id}/rollback", response_model=MappingVersionResponse)
def rollback(
    template_id: UUID,
    payload: RollbackMappingRequest,
    user: User = Depends(finance_user),
    db: Session = Depends(get_db),
) -> MappingVersion:
    try:
        return rollback_mapping(db, template_id, payload.version_id, user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

