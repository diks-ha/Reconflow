"""Rate history, returns evidence, claims lifecycle, audit, and exposure attribution.

Revision ID: 0004_finance_modules
Revises: 0003_financial_reconciliation
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_finance_modules"
down_revision = "0003_financial_reconciliation"
branch_labels = None
depends_on = None
MONEY = sa.Numeric(14, 2, asdecimal=True)


def upgrade() -> None:
    op.add_column("returns", sa.Column("courier_partner", sa.String(120), nullable=True))
    op.create_check_constraint("ck_rate_card_percentage_nonnegative", "rate_cards", "percentage_charge >= 0")
    op.add_column("rate_cards", sa.Column("version_number", sa.Integer(), server_default="1", nullable=False))
    op.add_column("rate_cards", sa.Column("supersedes_id", sa.Uuid(), nullable=True))
    op.add_column("rate_cards", sa.Column("created_by", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_rate_cards_supersedes", "rate_cards", "rate_cards", ["supersedes_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_rate_cards_created_by", "rate_cards", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.add_column("reconciliation_results", sa.Column("partner_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_reconciliation_results_partner", "reconciliation_results", "partners", ["partner_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_reconciliation_results_partner_id", "reconciliation_results", ["partner_id"])
    op.add_column("claims", sa.Column("partner_id", sa.Uuid(), nullable=True))
    op.alter_column("claims", "amount", existing_type=MONEY, nullable=True)
    op.add_column("claims", sa.Column("recovered_amount", MONEY, server_default="0.00", nullable=False))
    op.add_column("claims", sa.Column("assigned_reviewer_id", sa.Uuid(), nullable=True))
    op.add_column("claims", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_foreign_key("fk_claims_partner", "claims", "partners", ["partner_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_claims_reviewer", "claims", "users", ["assigned_reviewer_id"], ["id"], ondelete="SET NULL")
    op.create_check_constraint("ck_claims_recovery_range", "claims", "recovered_amount >= 0 AND (amount IS NULL OR recovered_amount <= amount)")
    op.create_index("ix_claims_partner_id", "claims", ["partner_id"])

    op.create_table("rate_card_history",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("rate_card_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rate_card_id"], ["rate_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("rate_card_id", "version_number", name="uq_rate_card_history_version"))
    op.create_index("ix_rate_card_history_rate_card_id", "rate_card_history", ["rate_card_id"])

    op.create_table("claim_evidence",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("source_import_id", sa.Uuid(), nullable=True), sa.Column("transaction_id", sa.String(120)),
        sa.Column("source_row_number", sa.Integer()), sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_import_id"], ["imports.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_claim_evidence_claim_id", "claim_evidence", ["claim_id"])
    op.create_table("claim_notes",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False), sa.Column("note", sa.String(4000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_claim_notes_claim_id", "claim_notes", ["claim_id"])
    op.create_table("audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(60), nullable=False), sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.String(120), nullable=False), sa.Column("before_json", sa.JSON()), sa.Column("after_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id", "created_at"])


def downgrade() -> None:
    op.drop_column("returns", "courier_partner")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_claim_notes_claim_id", table_name="claim_notes")
    op.drop_table("claim_notes")
    op.drop_index("ix_claim_evidence_claim_id", table_name="claim_evidence")
    op.drop_table("claim_evidence")
    op.drop_index("ix_rate_card_history_rate_card_id", table_name="rate_card_history")
    op.drop_table("rate_card_history")
    op.drop_constraint("ck_rate_card_percentage_nonnegative", "rate_cards", type_="check")
    op.drop_index("ix_claims_partner_id", table_name="claims")
    op.drop_constraint("ck_claims_recovery_range", "claims", type_="check")
    op.drop_constraint("fk_claims_reviewer", "claims", type_="foreignkey")
    op.drop_constraint("fk_claims_partner", "claims", type_="foreignkey")
    op.drop_column("claims", "updated_at")
    op.drop_column("claims", "assigned_reviewer_id")
    op.drop_column("claims", "recovered_amount")
    op.drop_column("claims", "partner_id")
    op.alter_column("claims", "amount", existing_type=MONEY, nullable=False)
    op.drop_index("ix_reconciliation_results_partner_id", table_name="reconciliation_results")
    op.drop_constraint("fk_reconciliation_results_partner", "reconciliation_results", type_="foreignkey")
    op.drop_column("reconciliation_results", "partner_id")
    op.drop_constraint("fk_rate_cards_created_by", "rate_cards", type_="foreignkey")
    op.drop_constraint("fk_rate_cards_supersedes", "rate_cards", type_="foreignkey")
    op.drop_column("rate_cards", "created_by")
    op.drop_column("rate_cards", "supersedes_id")
    op.drop_column("rate_cards", "version_number")
