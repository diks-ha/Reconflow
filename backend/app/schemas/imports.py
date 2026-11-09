from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.imports.constants import PartnerType, ReportType


class PartnerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    partner_type: PartnerType

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Partner name cannot be blank")
        return value


class PartnerResponse(BaseModel):
    id: UUID
    name: str
    partner_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MappingItem(BaseModel):
    source_column: str = Field(min_length=1, max_length=255)
    canonical_field: str | None = Field(default=None, max_length=60)


class ApproveMappingRequest(BaseModel):
    template_name: str = Field(min_length=1, max_length=120)
    mappings: list[MappingItem] = Field(min_length=1, max_length=200)

    @field_validator("template_name")
    @classmethod
    def validate_template_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Template name cannot be blank")
        return value


class ApplyTemplateRequest(BaseModel):
    mapping_version_id: UUID


class RollbackMappingRequest(BaseModel):
    version_id: UUID


class ImportResponse(BaseModel):
    id: UUID
    partner_id: UUID
    report_type: str
    original_filename: str
    file_size: int
    file_format: str
    file_hash: str
    status: str
    headers: list[str]
    row_count: int | None
    mapping_version_id: UUID | None
    validation_report: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PreviewResponse(BaseModel):
    import_id: UUID
    headers: list[str]
    rows: list[dict[str, str]]


class SuggestionItem(BaseModel):
    source_column: str
    canonical_field: str | None
    confidence: float = Field(ge=0, le=100)
    explanation: str
    uncertain: bool


class MappingSuggestionResponse(BaseModel):
    mode: str
    message: str
    suggestions: list[SuggestionItem]


class MappingVersionResponse(BaseModel):
    id: UUID
    template_id: UUID
    version_number: int
    parent_version_id: UUID | None
    mappings: list[dict]
    approved_by: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MappingTemplateResponse(BaseModel):
    id: UUID
    partner_id: UUID
    report_type: str
    name: str
    created_at: datetime
    latest_version: MappingVersionResponse | None

