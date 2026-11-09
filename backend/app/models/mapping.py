from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class MappingTemplate(Base):
    __tablename__ = "mapping_templates"
    __table_args__ = (
        UniqueConstraint("partner_id", "report_type", "name", name="uq_mapping_template_scope_name"),
        CheckConstraint(
            "report_type IN ('orders', 'marketplace_settlement', 'cod_remittance', 'courier_freight_invoice', 'warehouse_return_receipt')",
            name="ck_mapping_template_report_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MappingVersion(Base):
    __tablename__ = "mapping_versions"
    __table_args__ = (UniqueConstraint("template_id", "version_number", name="uq_mapping_version_number"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    template_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("mapping_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_import_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("imports.id", ondelete="SET NULL"), nullable=True)
    parent_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("mapping_versions.id", ondelete="SET NULL"), nullable=True)
    mappings: Mapped[list] = mapped_column(JSON, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

