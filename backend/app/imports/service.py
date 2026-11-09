from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.imports.file_service import (
    ImportFileError,
    finalize_upload,
    inspect_file,
    save_upload_stream,
    validate_extension,
    validate_mapped_file,
)
from app.imports.constants import STANDARD_FIELDS
from app.models.column_mapping import ColumnMapping
from app.models.import_record import ImportRecord
from app.models.mapping import MappingTemplate, MappingVersion
from app.models.partner import Partner
from app.models.user import User


class DuplicateImportError(ValueError):
    def __init__(self, import_id: UUID):
        self.import_id = import_id
        super().__init__("This file has already been imported")


def create_partner(db: Session, name: str, partner_type: str) -> Partner:
    partner = Partner(name=name.strip(), partner_type=partner_type)
    db.add(partner)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("A partner with this name already exists") from None
    db.refresh(partner)
    return partner


def save_import(db: Session, upload, original_filename: str, partner_id: UUID, report_type: str, user: User) -> ImportRecord:
    safe_name = Path(original_filename.replace("\\", "/")).name[:255]
    extension = validate_extension(safe_name)
    temporary, file_hash, size, final_path = save_upload_stream(upload, safe_name)
    try:
        duplicate = db.scalar(select(ImportRecord).where(ImportRecord.file_hash == file_hash))
        if duplicate is not None:
            raise DuplicateImportError(duplicate.id)
        headers, preview_rows = inspect_file(temporary, extension)
        record = ImportRecord(
            uploaded_by=user.id,
            partner_id=partner_id,
            report_type=report_type,
            original_filename=safe_name,
            storage_key=final_path,
            file_hash=file_hash,
            file_size=size,
            file_format=extension.removeprefix("."),
            status="UPLOADED",
            headers=headers,
            preview_rows=preview_rows,
        )
        db.add(record)
        db.flush()
        finalize_upload(temporary, final_path)
        db.commit()
        db.refresh(record)
        return record
    except IntegrityError:
        db.rollback()
        temporary.unlink(missing_ok=True)
        duplicate = db.scalar(select(ImportRecord).where(ImportRecord.file_hash == file_hash))
        if duplicate:
            raise DuplicateImportError(duplicate.id) from None
        Path(final_path).unlink(missing_ok=True)
        raise ImportFileError("The import could not be saved because of a database constraint") from None
    except Exception:
        db.rollback()
        temporary.unlink(missing_ok=True)
        raise


def approve_mapping(
    db: Session,
    record: ImportRecord,
    user: User,
    template_name: str,
    mappings: list[dict[str, str | None]],
) -> MappingVersion:
    source_columns = set(record.headers)
    seen_sources: set[str] = set()
    seen_targets: set[str] = set()
    normalized: list[dict[str, str | None]] = []
    for mapping in mappings:
        source = mapping["source_column"].strip()
        target = mapping.get("canonical_field")
        if source not in source_columns:
            raise ValueError(f"Source column is not present in this import: {source}")
        if source in seen_sources:
            raise ValueError(f"Source column was mapped more than once: {source}")
        if target is not None and target not in STANDARD_FIELDS:
            raise ValueError(f"Unsupported standardized field: {target}")
        if target is not None and target in seen_targets:
            raise ValueError(f"More than one source column maps to {target}")
        seen_sources.add(source)
        if target:
            seen_targets.add(target)
        normalized.append({"source_column": source, "canonical_field": target})
    if not any(item["canonical_field"] for item in normalized):
        raise ValueError("At least one source column must be mapped")

    template = db.scalar(
        select(MappingTemplate).where(
            MappingTemplate.partner_id == record.partner_id,
            MappingTemplate.report_type == record.report_type,
            MappingTemplate.name == template_name.strip(),
        )
    )
    if template is None:
        template = MappingTemplate(
            partner_id=record.partner_id,
            report_type=record.report_type,
            name=template_name.strip(),
            created_by=user.id,
        )
        db.add(template)
        db.flush()
    version_number = db.scalar(select(func.max(MappingVersion.version_number)).where(MappingVersion.template_id == template.id)) or 0
    version = MappingVersion(
        template_id=template.id,
        version_number=version_number + 1,
        source_import_id=record.id,
        mappings=normalized,
        created_by=user.id,
        approved_by=user.id,
    )
    db.add(version)
    db.flush()
    db.add_all([
        ColumnMapping(mapping_version_id=version.id, source_column=m["source_column"], canonical_field=m["canonical_field"])
        for m in normalized
    ])
    record.mapping_version_id = version.id
    record.status = "MAPPED"
    record.validation_report = None
    record.error_message = None
    db.commit()
    db.refresh(version)
    return version


def apply_mapping_template(db: Session, record: ImportRecord, version_id: UUID) -> MappingVersion:
    version = db.get(MappingVersion, version_id)
    if version is None:
        raise LookupError("Mapping version not found")
    template = db.get(MappingTemplate, version.template_id)
    if template.partner_id != record.partner_id or template.report_type != record.report_type:
        raise ValueError("Mapping template does not match this partner and report type")
    if any(item["source_column"] not in record.headers for item in version.mappings):
        raise ValueError("Mapping version contains columns that are not present in this file")
    record.mapping_version_id = version.id
    record.status = "MAPPED"
    record.validation_report = None
    db.commit()
    db.refresh(record)
    return version


def validate_import(db: Session, record: ImportRecord) -> dict:
    if record.mapping_version_id is None:
        raise ValueError("Approve or apply a mapping before validating this import")
    version = db.get(MappingVersion, record.mapping_version_id)
    report = validate_mapped_file(Path(record.storage_key), f".{record.file_format}", version.mappings)
    record.row_count = report["row_count"]
    record.validation_report = report
    record.status = "VALIDATED" if report["valid"] else "INVALID"
    record.error_message = None if report["valid"] else "Mapped values contain invalid values; review the validation report"
    db.commit()
    db.refresh(record)
    return report


def list_mapping_templates(db: Session, partner_id: UUID | None = None, report_type: str | None = None) -> list[MappingTemplate]:
    query = select(MappingTemplate)
    if partner_id:
        query = query.where(MappingTemplate.partner_id == partner_id)
    if report_type:
        query = query.where(MappingTemplate.report_type == report_type)
    return list(db.scalars(query.order_by(MappingTemplate.created_at.desc())))


def list_versions(db: Session, template_id: UUID) -> list[MappingVersion]:
    return list(db.scalars(select(MappingVersion).where(MappingVersion.template_id == template_id).order_by(MappingVersion.version_number.desc())))


def rollback_mapping(db: Session, template_id: UUID, source_version_id: UUID, user: User) -> MappingVersion:
    template = db.get(MappingTemplate, template_id)
    source = db.get(MappingVersion, source_version_id)
    if template is None or source is None or source.template_id != template.id:
        raise LookupError("Mapping template or version not found")
    latest_number = db.scalar(select(func.max(MappingVersion.version_number)).where(MappingVersion.template_id == template.id)) or 0
    version = MappingVersion(
        template_id=template.id,
        version_number=latest_number + 1,
        parent_version_id=source.id,
        mappings=source.mappings,
        created_by=user.id,
        approved_by=user.id,
    )
    db.add(version)
    db.flush()
    db.add_all([
        ColumnMapping(mapping_version_id=version.id, source_column=m["source_column"], canonical_field=m["canonical_field"])
        for m in source.mappings
    ])
    db.commit()
    db.refresh(version)
    return version
