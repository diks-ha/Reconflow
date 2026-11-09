from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class ColumnMapping(Base):
    __tablename__ = "column_mappings"
    __table_args__ = (UniqueConstraint("mapping_version_id", "source_column", name="uq_column_mapping_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    mapping_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("mapping_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_column: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_field: Mapped[str | None] = mapped_column(String(60), nullable=True)

