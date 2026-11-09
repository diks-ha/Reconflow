"""File imports, partners, mapping templates and mapping versions.

Revision ID: 0002_imports_mappings
Revises: 0001_initial_auth
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_imports_mappings"
down_revision = "0001_initial_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partners",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("partner_type", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_partners_name"),
        sa.CheckConstraint("partner_type IN ('MARKETPLACE', 'COURIER', 'QUICK_COMMERCE', 'WEBSITE', 'PAYMENT_PROVIDER', 'WAREHOUSE')", name="ck_partners_type"),
    )
    op.create_table(
        "imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("report_type", sa.String(length=40), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_format", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("preview_rows", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("mapping_version_id", sa.Uuid(), nullable=True),
        sa.Column("validation_report", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('UPLOADED', 'MAPPED', 'VALIDATED', 'INVALID', 'PROCESSING', 'PROCESSED', 'FAILED')", name="ck_imports_status"),
        sa.CheckConstraint("report_type IN ('orders', 'marketplace_settlement', 'cod_remittance', 'courier_freight_invoice', 'warehouse_return_receipt')", name="ck_imports_report_type"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_hash", name="uq_imports_file_hash"),
    )
    op.create_index("ix_imports_partner_type_created", "imports", ["partner_id", "report_type", "created_at"], unique=False)
    op.create_index("ix_imports_status", "imports", ["status"], unique=False)
    op.create_table(
        "mapping_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("report_type", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", "report_type", "name", name="uq_mapping_template_scope_name"),
        sa.CheckConstraint("report_type IN ('orders', 'marketplace_settlement', 'cod_remittance', 'courier_freight_invoice', 'warehouse_return_receipt')", name="ck_mapping_template_report_type"),
    )
    op.create_index("ix_mapping_templates_partner_id", "mapping_templates", ["partner_id"], unique=False)
    op.create_table(
        "mapping_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source_import_id", sa.Uuid(), nullable=True),
        sa.Column("parent_version_id", sa.Uuid(), nullable=True),
        sa.Column("mappings", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["mapping_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_import_id"], ["imports.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["mapping_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "version_number", name="uq_mapping_version_number"),
    )
    op.create_index("ix_mapping_versions_template_id", "mapping_versions", ["template_id"], unique=False)
    op.create_table(
        "column_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mapping_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_column", sa.String(length=255), nullable=False),
        sa.Column("canonical_field", sa.String(length=60), nullable=True),
        sa.ForeignKeyConstraint(["mapping_version_id"], ["mapping_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mapping_version_id", "source_column", name="uq_column_mapping_source"),
    )
    op.create_index("ix_column_mappings_mapping_version_id", "column_mappings", ["mapping_version_id"], unique=False)
    op.create_foreign_key(
        "fk_imports_mapping_version_id_mapping_versions",
        "imports", "mapping_versions", ["mapping_version_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_imports_mapping_version_id_mapping_versions", "imports", type_="foreignkey")
    op.drop_index("ix_column_mappings_mapping_version_id", table_name="column_mappings")
    op.drop_table("column_mappings")
    op.drop_index("ix_mapping_versions_template_id", table_name="mapping_versions")
    op.drop_table("mapping_versions")
    op.drop_index("ix_mapping_templates_partner_id", table_name="mapping_templates")
    op.drop_table("mapping_templates")
    op.drop_index("ix_imports_status", table_name="imports")
    op.drop_index("ix_imports_partner_type_created", table_name="imports")
    op.drop_table("imports")
    op.drop_table("partners")

