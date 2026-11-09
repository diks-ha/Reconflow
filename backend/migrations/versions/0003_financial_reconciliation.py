"""Deterministic financial reconciliation records and results.

Revision ID: 0003_financial_reconciliation
Revises: 0002_imports_mappings
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_financial_reconciliation"
down_revision = "0002_imports_mappings"
branch_labels = None
depends_on = None
MONEY = sa.Numeric(14, 2, asdecimal=True)


def upgrade() -> None:
    op.create_table("orders",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("order_id", sa.String(120), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False), sa.Column("channel", sa.String(80), nullable=False),
        sa.Column("payment_method", sa.String(40)), sa.Column("delivery_status", sa.String(60)),
        sa.Column("order_value", MONEY), sa.Column("expected_amount", MONEY), sa.Column("settlement_due_date", sa.Date()),
        sa.Column("payment_eligible", sa.Boolean(), nullable=False), sa.Column("return_status", sa.String(60)),
        sa.Column("return_id", sa.String(120)), sa.Column("return_deadline", sa.Date()), sa.Column("raw_source", sa.JSON(), nullable=False),
        sa.Column("tracking_id", sa.String(120)),
        sa.Column("source_import_id", sa.Uuid(), nullable=False), sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_import_id"], ["imports.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("channel", "order_id", name="uq_orders_channel_order"))
    op.create_index("ix_orders_order_id", "orders", ["order_id"])
    op.create_index("ix_orders_partner_order", "orders", ["partner_id", "order_id"])
    op.create_index("ix_orders_tracking_id", "orders", ["tracking_id"])

    for table, prefix in (("settlements", "settlement"), ("cod_remittances", "cod")):
        amount_name = "amount"
        op.create_table(table,
            sa.Column("id", sa.Uuid(), nullable=False), sa.Column("partner_id", sa.Uuid(), nullable=False),
            sa.Column("order_id", sa.String(120), nullable=False), sa.Column("transaction_id", sa.String(120)),
            sa.Column(amount_name, MONEY, nullable=False),
            *([sa.Column("gst_tcs", MONEY, nullable=False), sa.Column("income_tax_tds", MONEY, nullable=False)] if table == "settlements" else []),
            sa.Column("settled_at" if table == "settlements" else "remitted_at", sa.Date()),
            sa.Column("source_import_id", sa.Uuid(), nullable=False), sa.Column("source_row_number", sa.Integer(), nullable=False),
            sa.Column("raw_source", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["source_import_id"], ["imports.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("partner_id", "transaction_id", name=f"uq_{prefix}_partner_transaction"),
            sa.UniqueConstraint("source_import_id", "source_row_number", name=f"uq_{prefix}_import_row"))
        op.create_index(f"ix_{table}_order", table, ["order_id"])

    op.create_table("freight_invoices",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.String(120), nullable=False), sa.Column("transaction_id", sa.String(120)),
        sa.Column("tracking_id", sa.String(120)), sa.Column("courier_partner", sa.String(120)),
        sa.Column("billed_charge", MONEY, nullable=False), sa.Column("weight", sa.Numeric(12, 3, asdecimal=True)),
        sa.Column("source_import_id", sa.Uuid(), nullable=False), sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("raw_source", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_import_id"], ["imports.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("partner_id", "transaction_id", name="uq_freight_partner_transaction"),
        sa.UniqueConstraint("source_import_id", "source_row_number", name="uq_freight_import_row"))
    op.create_index("ix_freight_invoices_order", "freight_invoices", ["order_id"])
    op.create_index("ix_freight_invoices_tracking_id", "freight_invoices", ["tracking_id"])

    op.create_table("warehouse_receipts",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("order_id", sa.String(120), nullable=False),
        sa.Column("return_id", sa.String(120)), sa.Column("tracking_id", sa.String(120)), sa.Column("received_at", sa.Date()),
        sa.Column("source_import_id", sa.Uuid(), nullable=False), sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("raw_source", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["source_import_id"], ["imports.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("source_import_id", "source_row_number", name="uq_receipt_import_row"))
    op.create_index("ix_warehouse_receipts_order", "warehouse_receipts", ["order_id"])
    op.create_index("ix_warehouse_receipts_return_id", "warehouse_receipts", ["return_id"])
    op.create_index("ix_warehouse_receipts_tracking_id", "warehouse_receipts", ["tracking_id"])

    op.create_table("returns",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.String(120), nullable=False), sa.Column("return_id", sa.String(120)),
        sa.Column("return_status", sa.String(60), nullable=False), sa.Column("tracking_id", sa.String(120)),
        sa.Column("initiated_at", sa.Date()), sa.Column("deadline", sa.Date()),
        sa.Column("source_import_id", sa.Uuid(), nullable=False), sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("raw_source", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_import_id"], ["imports.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("partner_id", "return_id", name="uq_returns_partner_return"),
        sa.UniqueConstraint("source_import_id", "source_row_number", name="uq_returns_import_row"))
    for column in ("order_id", "tracking_id"):
        op.create_index(f"ix_returns_{column}", "returns", [column])

    op.create_table("rate_cards",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("channel", sa.String(80), nullable=False),
        sa.Column("courier_partner", sa.String(120), nullable=False), sa.Column("min_weight", sa.Numeric(12, 3, asdecimal=True), nullable=False),
        sa.Column("max_weight", sa.Numeric(12, 3, asdecimal=True)), sa.Column("forward_fee", MONEY, nullable=False),
        sa.Column("return_fee", MONEY, nullable=False), sa.Column("cod_fee", MONEY, nullable=False), sa.Column("fixed_charge", MONEY, nullable=False),
        sa.Column("percentage_charge", sa.Numeric(7, 4, asdecimal=True), nullable=False), sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()), sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("source_note", sa.String(120), nullable=False), sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("min_weight >= 0 AND (max_weight IS NULL OR max_weight >= min_weight)", name="ck_rate_card_weight_range"),
        sa.CheckConstraint("forward_fee >= 0 AND return_fee >= 0 AND cod_fee >= 0 AND fixed_charge >= 0", name="ck_rate_card_fees_nonnegative"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_rate_card_effective_range"))
    op.create_index("ix_rate_cards_lookup", "rate_cards", ["channel", "courier_partner", "effective_from", "effective_to"])

    op.create_table("reconciliation_runs",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("threshold", MONEY, nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"))
    op.create_table("reconciliation_results",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.String(120), nullable=False), sa.Column("status", sa.String(40), nullable=False),
        sa.Column("expected_amount", MONEY), sa.Column("received_amount", MONEY), sa.Column("difference", MONEY),
        sa.Column("gst_tcs", MONEY, nullable=False), sa.Column("income_tax_tds", MONEY, nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False), sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.String(2000), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["reconciliation_runs.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "order_id", name="uq_reconciliation_run_order"))
    op.create_index("ix_reconciliation_results_order_id", "reconciliation_results", ["order_id"])
    op.create_index("ix_reconciliation_results_status", "reconciliation_results", ["status"])
    op.create_table("claims",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("reconciliation_result_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.String(120), nullable=False), sa.Column("category", sa.String(40), nullable=False),
        sa.Column("amount", MONEY, nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["reconciliation_result_id"], ["reconciliation_results.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("order_id", "category", name="uq_claim_order_category"))


def downgrade() -> None:
    op.drop_table("claims")
    op.drop_index("ix_reconciliation_results_status", table_name="reconciliation_results")
    op.drop_index("ix_reconciliation_results_order_id", table_name="reconciliation_results")
    op.drop_table("reconciliation_results")
    op.drop_table("reconciliation_runs")
    op.drop_index("ix_rate_cards_lookup", table_name="rate_cards")
    op.drop_table("rate_cards")
    for column in ("tracking_id", "order_id"):
        op.drop_index(f"ix_returns_{column}", table_name="returns")
    op.drop_table("returns")
    op.drop_index("ix_warehouse_receipts_tracking_id", table_name="warehouse_receipts")
    op.drop_index("ix_warehouse_receipts_return_id", table_name="warehouse_receipts")
    op.drop_index("ix_warehouse_receipts_order", table_name="warehouse_receipts")
    op.drop_table("warehouse_receipts")
    op.drop_index("ix_freight_invoices_tracking_id", table_name="freight_invoices")
    op.drop_index("ix_freight_invoices_order", table_name="freight_invoices")
    op.drop_table("freight_invoices")
    for table in ("cod_remittances", "settlements"):
        op.drop_index(f"ix_{table}_order", table_name=table)
        op.drop_table(table)
    op.drop_index("ix_orders_partner_order", table_name="orders")
    op.drop_index("ix_orders_tracking_id", table_name="orders")
    op.drop_index("ix_orders_order_id", table_name="orders")
    op.drop_table("orders")
