"""Generate a deterministic 100k-order dataset and time the import-to-reconciliation pipeline.

Run from backend with: python benchmarks/benchmark_pipeline.py
The benchmark uses a temporary SQLite database because it must not modify a configured DB.
It generates fictional customer/order identifiers and deletes artifacts on exit.
"""
from __future__ import annotations

import csv
import os
import re
import sys
import tempfile
import time
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("JWT_SECRET_KEY", "benchmark-secret-key-longer-than-thirty-two-characters")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.database.base import Base
from app.imports.service import approve_mapping, save_import, validate_import
from app.models.finance import Claim, ReconciliationResult
from app.models.import_record import ImportRecord
from app.models.partner import Partner
from app.models.role import Role
from app.models.user import User, UserRole
from app.reconciliation.imports import load_reconciliation_inputs, process_validated_import
from app.reconciliation.service import execute_and_persist
import app.imports.file_service as file_service

ORDER_COUNT = 100_000
AS_OF = date(2026, 11, 9)
PREPAID_MAPPING = [
    {"source_column": "Order ID", "canonical_field": "order_id"},
    {"source_column": "Channel", "canonical_field": "channel"},
    {"source_column": "Payment Method", "canonical_field": "payment_method"},
    {"source_column": "Delivery Status", "canonical_field": "delivery_status"},
    {"source_column": "Order Value", "canonical_field": "order_value"},
    {"source_column": "Expected Amount", "canonical_field": "expected_amount"},
    {"source_column": "Settlement Due Date", "canonical_field": "settlement_due_date"},
]
SETTLEMENT_MAPPING = [
    {"source_column": "Order ID", "canonical_field": "order_id"},
    {"source_column": "Transaction ID", "canonical_field": "transaction_id"},
    {"source_column": "Net Settlement", "canonical_field": "received_amount"},
    {"source_column": "GST TCS", "canonical_field": "gst_tcs"},
    {"source_column": "Income Tax TDS", "canonical_field": "income_tax_tds"},
    {"source_column": "Settlement Date", "canonical_field": "settlement_date"},
]
COD_MAPPING = [
    {"source_column": "Order ID", "canonical_field": "order_id"},
    {"source_column": "Transaction ID", "canonical_field": "transaction_id"},
    {"source_column": "Remittance Amount", "canonical_field": "received_amount"},
    {"source_column": "Remittance Date", "canonical_field": "remittance_date"},
]


def make_dataset(root: Path) -> tuple[Path, Path, Path, int]:
    order_path, settlement_path, cod_path = root / "orders.csv", root / "settlements.csv", root / "cod.csv"
    settlement_rows = cod_rows = 0
    with order_path.open("w", newline="", encoding="utf-8") as order_file, \
         settlement_path.open("w", newline="", encoding="utf-8") as settlement_file, \
         cod_path.open("w", newline="", encoding="utf-8") as cod_file:
        orders = csv.writer(order_file)
        settlements = csv.writer(settlement_file)
        cods = csv.writer(cod_file)
        orders.writerow(["Order ID", "Channel", "Payment Method", "Delivery Status", "Order Value", "Expected Amount", "Settlement Due Date"])
        settlements.writerow(["Order ID", "Transaction ID", "Net Settlement", "GST TCS", "Income Tax TDS", "Settlement Date"])
        cods.writerow(["Order ID", "Transaction ID", "Remittance Amount", "Remittance Date"])
        for index in range(ORDER_COUNT):
            order_id = f"BENCH-{index + 1:06d}"
            expected = Decimal("1000.00") + Decimal(index % 41) * Decimal("10.00")
            order_value = expected + Decimal("250.00")
            payment_method = "Prepaid" if index < 80_000 else "COD"
            orders.writerow([order_id, "Marketplace 1", payment_method, "Delivered", f"{order_value:.2f}", f"{expected:.2f}", "2026-10-01"])
            if index < 5_000 or 80_000 <= index < 85_000:
                continue  # past-due, delivered, no payment row
            if 5_000 <= index < 10_000:
                amounts = [expected - Decimal("50.00")]
            elif 10_000 <= index < 15_000:
                half = (expected - Decimal("20.00")) / Decimal("2.00")
                amounts = [half, expected - Decimal("20.00") - half]
            elif 80_000 <= index < 90_000:
                amounts = [expected - Decimal("30.00")]
            else:
                amounts = [expected]
            for payment_index, amount in enumerate(amounts, start=1):
                transaction_id = f"TX-{index + 1:06d}-{payment_index}"
                if payment_method == "COD":
                    cods.writerow([order_id, transaction_id, f"{amount:.2f}", "2026-10-28"])
                    cod_rows += 1
                else:
                    tcs = (amount * Decimal("0.005")).quantize(Decimal("0.01"))
                    tds = (amount * Decimal("0.010")).quantize(Decimal("0.01"))
                    settlements.writerow([order_id, transaction_id, f"{amount:.2f}", f"{tcs:.2f}", f"{tds:.2f}", "2026-10-28"])
                    settlement_rows += 1
    return order_path, settlement_path, cod_path, settlement_rows + cod_rows


def main() -> None:
    artifact_root = Path(__file__).resolve().parents[1] / ".test-storage"
    artifact_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reconflow-bench-", dir=artifact_root) as temp:
        root = Path(temp)
        data_dir = root / "uploads"
        data_dir.mkdir()
        file_service.get_settings = lambda: SimpleNamespace(upload_dir=data_dir, max_upload_size_mb=250)
        engine = create_engine(f"sqlite+pysqlite:///{root / 'benchmark.sqlite'}")
        statement_count = 0
        phase = "setup"
        phase_counts: dict[str, int] = {}
        sql_categories: Counter[str] = Counter()

        @event.listens_for(engine, "after_cursor_execute")
        def count_statements(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
            nonlocal statement_count
            statement_count += 1
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            normalized = statement.lstrip().lower()
            match = re.search(r"\b(?:from|into|update)\s+[\"`]?([a-z_]+)", normalized)
            sql_categories[f"{normalized.split(None, 1)[0]} {match.group(1) if match else 'other'}"] += 1

        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        generation_started = time.perf_counter()
        order_file, settlement_file, cod_file, payment_count = make_dataset(root)
        generation_seconds = time.perf_counter() - generation_started

        with Session.begin() as db:
            executive_role = Role(name="FINANCE_EXECUTIVE", description="Finance Executive")
            db.add(executive_role)
            user = User(email="benchmark@example.com", full_name="Benchmark Finance User", password_hash=hash_password("benchmark-password-2026"))
            partner = Partner(name="Benchmark Marketplace", partner_type="MARKETPLACE")
            db.add_all([user, partner])
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=executive_role.id))
            user_id, partner_id = user.id, partner.id

        with Session() as db:
            user, partner = db.get(User, user_id), db.get(Partner, partner_id)
            phase = "upload"
            upload_started = time.perf_counter()
            records = []
            for path, report_type in (
                (order_file, "orders"),
                (settlement_file, "marketplace_settlement"),
                (cod_file, "cod_remittance"),
            ):
                if path.stat().st_size == 0:
                    continue
                with path.open("rb") as source:
                    records.append(save_import(db, SimpleNamespace(file=source), path.name, partner.id, report_type, user))
            upload_seconds = time.perf_counter() - upload_started

            phase = "mapping_validation"
            map_started = time.perf_counter()
            mappings = {"orders": PREPAID_MAPPING, "marketplace_settlement": SETTLEMENT_MAPPING, "cod_remittance": COD_MAPPING}
            for record in records:
                version = approve_mapping(db, record, user, f"Benchmark {record.report_type}", mappings[record.report_type])
                validate_import(db, record)
                if record.status != "VALIDATED":
                    raise RuntimeError(f"Unexpected validation failure for {record.report_type}: {record.validation_report}")
            mapping_validation_seconds = time.perf_counter() - map_started

            phase = "batch_import"
            import_started = time.perf_counter()
            for record in records:
                process_validated_import(db, record.id)
            import_processing_seconds = time.perf_counter() - import_started

            phase = "reconciliation"
            reconciliation_started = time.perf_counter()
            inputs = load_reconciliation_inputs(db, [record.id for record in records], AS_OF, Decimal("10.00"))
            run, claims_created = execute_and_persist(db, user, inputs)
            reconciliation_seconds = time.perf_counter() - reconciliation_started

            phase = "verification"
            result_count = db.scalar(select(func.count()).select_from(ReconciliationResult).where(ReconciliationResult.run_id == run.id))
            claim_count = db.scalar(select(func.count()).select_from(Claim))
            summary = run.summary
            if result_count != ORDER_COUNT:
                raise AssertionError(f"Expected {ORDER_COUNT} results, got {result_count}")
            if claim_count != claims_created:
                raise AssertionError(f"Claim count mismatch: database={claim_count}, inserted={claims_created}")

        pipeline_seconds = upload_seconds + mapping_validation_seconds + import_processing_seconds + reconciliation_seconds
        print("Benchmark database: SQLite file in temporary storage")
        print(f"Source rows: {ORDER_COUNT:,} orders + {payment_count:,} payment rows")
        print(f"Generated source files in: {generation_seconds:.2f}s")
        print(f"Upload + hash + header/preview: {upload_seconds:.2f}s")
        print(f"Mapping approval + validation: {mapping_validation_seconds:.2f}s")
        print(f"Batch import processing: {import_processing_seconds:.2f}s")
        print(f"DB load + reconciliation + persistence: {reconciliation_seconds:.2f}s")
        print(f"Complete import-to-reconciliation: {pipeline_seconds:.2f}s ({ORDER_COUNT / pipeline_seconds:,.0f} orders/s)")
        print(f"End-to-end including generation: {generation_seconds + pipeline_seconds:.2f}s")
        print(f"Saved reconciliation results: {result_count:,}; claims created: {claims_created:,}; summary: {summary['statuses']}")
        print(f"SQL cursor executions across setup and pipeline: {statement_count:,}")
        print(f"SQL executions by phase: {phase_counts}")
        print(f"SQL executions by table/type: {sql_categories.most_common(10)}")
        engine.dispose()


if __name__ == "__main__":
    main()
