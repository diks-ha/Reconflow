from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class ImportRecord(Base):
    __tablename__ = "imports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('UPLOADED', 'MAPPED', 'VALIDATED', 'INVALID', 'PROCESSING', 'PROCESSED', 'FAILED')",
            name="ck_imports_status",
        ),
        CheckConstraint(
            "report_type IN ('orders', 'marketplace_settlement', 'cod_remittance', 'courier_freight_invoice', 'warehouse_return_receipt')",
            name="ck_imports_report_type",
        ),
        Index("ix_imports_partner_type_created", "partner_id", "report_type", "created_at"),
        Index("ix_imports_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    uploaded_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    partner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False)
    report_type: Mapped[str] = mapped_column(String(40), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    file_size: Mapped[int] = mapped_column(nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UPLOADED")
    headers: Mapped[list] = mapped_column(JSON, nullable=False)
    preview_rows: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    row_count: Mapped[int | None] = mapped_column(nullable=True)
    mapping_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("mapping_versions.id", ondelete="SET NULL", use_alter=True, name="fk_imports_mapping_version_id_mapping_versions"),
        nullable=True,
    )
    validation_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

