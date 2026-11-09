"""Reproducible end-to-end import and reconciliation benchmark.

By default, generates 100,000 source rows (50k orders + 50k settlements) in a
temporary directory and runs upload, mapping, validation, import, load, reconcile,
claim generation and persistence against a temporary SQLite database. Set
DATABASE_URL externally to benchmark a configured database; do not point this at
production because the script creates and populates a fresh schema.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import random
import sys
import tempfile
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace


def _write_rows(path: Path, headers: list[str], rows) -> None:
    import csv
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)


def generate_dataset(folder: Path, total_rows: int, seed: int) -> tuple[Path, Path, int, int]:
    orders_count = total_rows // 2
    settlements_count = total_rows - orders_count
    rng = random.Random(seed)
    orders_path = folder / "benchmark_orders.csv"
    settlements_path = folder / "benchmark_settlements.csv"

    def orders():
        for n in range(orders_count):
            order_id = f"RF-BENCH-{n + 1:07d}"
            order_value = Decimal(rng.randrange(60000, 500000)) / 100
            expected = Decimal(rng.randrange(50000, 480000)) / 100
            yield [order_id, "Marketplace 1", "Prepaid", "Delivered", f"{order_value:.2f}",
                   f"{expected:.2f}", (date(2026, 10, 1) + timedelta(days=n % 31)).isoformat()]

    # Reconstruct amounts with the same seed/order stream to keep the generated
    # payment report consistent without holding 50k source objects in memory.
    def settlements():
        payment_rng = random.Random(seed)
        for n in range(orders_count):
            payment_rng.randrange(60000, 500000)  # consume the order-value draw
            expected = Decimal(payment_rng.randrange(50000, 480000)) / 100
            short_paid = n % 20 == 0  # deterministic, realistic 5% exception rate
            received = expected - Decimal("35.00") if short_paid else expected
            tcs = (received * Decimal("0.005")).quantize(Decimal("0.01"))
            tds = (received * Decimal("0.001")).quantize(Decimal("0.01"))
            yield [f"RF-BENCH-{n + 1:07d}", f"SET-{n + 1:07d}", f"{received:.2f}",
                   f"{tcs:.2f}", f"{tds:.2f}", "2026-11-08"]

    _write_rows(orders_path,
                ["order_id", "channel", "payment_method", "delivery_status", "order_value", "expected_amount", "settlement_due_date"],
                orders())
    _write_rows(settlements_path,
                ["order_id", "transaction_id", "received_amount", "gst_tcs", "income_tax_tds", "settlement_date"],
                settlements())
    return orders_path, settlements_path, orders_count, settlements_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100_000, help="Total source rows across order and settlement CSVs")
    parser.add_argument("--seed", type=int, default=20261109)
    parser.add_argument("--output", type=Path, help="Optional directory to retain generated source files")
    parser.add_argument("--use-configured-database", action="store_true",
                        help="Use DATABASE_URL from environment/.env (must point to an empty, disposable database)")
    args = parser.parse_args()
    if args.rows < 2:
        parser.error("--rows must be at least 2")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    os.environ.setdefault("JWT_SECRET_KEY", "reconflow-benchmark-placeholder-secret-000000")
    project_root = Path(__file__).resolve().parents[1]
    temporary = tempfile.TemporaryDirectory(prefix=".benchmark-", dir=project_root)
    temp_root = Path(temporary.name)
    if not args.use_configured_database:
        os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{(temp_root / 'benchmark.db').as_posix()}"
    os.environ["UPLOAD_DIR"] = str(temp_root / "uploads")
    os.environ.setdefault("MAX_UPLOAD_SIZE_MB", "512")

    from app.core.config import get_settings
    get_settings.cache_clear()
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    from sqlalchemy import func, select
    from app.core.security import hash_password
    from app.database.session import Base, SessionLocal, engine
    from app.models.finance import Claim, Order, ReconciliationResult, Settlement
    from app.models.import_record import ImportRecord
    from app.models.partner import Partner
    from app.models.role import Role
    from app.models.user import User, UserRole
    from app.imports.service import approve_mapping, save_import, validate_import
    from app.reconciliation.imports import load_reconciliation_inputs, process_validated_import
    import app.reconciliation.service as persistence_service

    source_folder = args.output.resolve() if args.output else temp_root / "source"
    source_folder.mkdir(parents=True, exist_ok=True)
    generation_start = time.perf_counter()
    order_file, settlement_file, order_count, settlement_count = generate_dataset(source_folder, args.rows, args.seed)
    generation_seconds = time.perf_counter() - generation_start
    generated_bytes = order_file.stat().st_size + settlement_file.stat().st_size

    Base.metadata.create_all(engine)
    total_input_rows = 0
    timings: dict[str, float] = {}
    pipeline_start = time.perf_counter()
    with SessionLocal() as db:
        role = Role(name="FINANCE_EXECUTIVE", description="Finance Executive")
        user = User(email="benchmark@example.test", full_name="Benchmark Finance",
                    password_hash=hash_password("benchmark-only-password"))
        partner = Partner(name="Benchmark Marketplace", partner_type="MARKETPLACE")
        db.add_all([role, user, partner])
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()

        imports: list[ImportRecord] = []
        import_specs = [
            (order_file, "orders", [
                ("order_id", "order_id"), ("channel", "channel"), ("payment_method", "payment_method"),
                ("delivery_status", "delivery_status"), ("order_value", "order_value"),
                ("expected_amount", "expected_amount"), ("settlement_due_date", "settlement_due_date"),
            ]),
            (settlement_file, "marketplace_settlement", [
                ("order_id", "order_id"), ("transaction_id", "transaction_id"),
                ("received_amount", "received_amount"), ("gst_tcs", "gst_tcs"),
                ("income_tax_tds", "income_tax_tds"), ("settlement_date", "settlement_date"),
            ]),
        ]
        upload_map_validation = 0.0
        processing = 0.0
        for file_path, report_type, pairs in import_specs:
            step_start = time.perf_counter()
            with file_path.open("rb") as source:
                upload = SimpleNamespace(file=source, filename=file_path.name)
                record = save_import(db, upload, file_path.name, partner.id, report_type, user)
            mappings = [{"source_column": source, "canonical_field": target} for source, target in pairs]
            approve_mapping(db, record, user, f"Benchmark {report_type} mapping", mappings)
            report = validate_import(db, record)
            if not report["valid"] or report["row_count"] != (order_count if report_type == "orders" else settlement_count):
                raise RuntimeError(f"Import validation failed for {report_type}")
            upload_map_validation += time.perf_counter() - step_start

            step_start = time.perf_counter()
            processed = process_validated_import(db, record.id)
            if processed["rows_processed"] != report["row_count"]:
                raise RuntimeError(f"Processed row count mismatch for {report_type}")
            processing += time.perf_counter() - step_start
            imports.append(record)
            total_input_rows += report["row_count"]
        timings["upload_mapping_validation_seconds"] = upload_map_validation
        timings["import_processing_seconds"] = processing

        step_start = time.perf_counter()
        inputs = load_reconciliation_inputs(db, [item.id for item in imports], date(2026, 11, 9), Decimal("10.00"))
        timings["database_load_and_input_build_seconds"] = time.perf_counter() - step_start

        original_reconcile = persistence_service.reconcile
        def timed_reconcile(payload):
            start = time.perf_counter()
            result = original_reconcile(payload)
            timings["engine_calculation_seconds"] = time.perf_counter() - start
            return result
        persistence_service.reconcile = timed_reconcile
        step_start = time.perf_counter()
        run, claims_created = persistence_service.execute_and_persist(db, user, inputs)
        timings["reconciliation_and_batched_persistence_seconds"] = time.perf_counter() - step_start
        timings["database_persistence_seconds_estimate"] = max(
            timings["reconciliation_and_batched_persistence_seconds"] - timings.get("engine_calculation_seconds", 0), 0.0
        )
        persistence_service.reconcile = original_reconcile

        database_counts = {
            "orders": db.scalar(select(func.count()).select_from(Order)),
            "settlements": db.scalar(select(func.count()).select_from(Settlement)),
            "results_for_run": db.scalar(select(func.count()).select_from(ReconciliationResult).where(ReconciliationResult.run_id == run.id)),
            "claims_created_by_run": claims_created,
            "claims_total": db.scalar(select(func.count()).select_from(Claim)),
        }

    pipeline_seconds = time.perf_counter() - pipeline_start
    report = {
        "benchmark": "ReconFlow 100k import and reconciliation",
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "database_dialect": engine.dialect.name,
        "schema_method": "SQLAlchemy metadata create_all; migration/live PostgreSQL benchmark was not used unless DATABASE_URL was supplied",
        "input_rows_total": total_input_rows,
        "orders_rows": order_count,
        "settlement_rows": settlement_count,
        "generated_file_bytes": generated_bytes,
        "short_paid_rate": 0.05,
        "gst_tcs_rate": 0.005,
        "income_tax_tds_rate": 0.001,
        "seed": args.seed,
        "generation_seconds": round(generation_seconds, 3),
        "pipeline_seconds_excluding_generation": round(pipeline_seconds, 3),
        "source_rows_per_second": round(total_input_rows / pipeline_seconds, 1),
        "timings": {key: round(value, 3) for key, value in timings.items()},
        "database_counts": database_counts,
        "note": "Synthetic realistic test data; timing reflects this host and selected database only, not a production service-level guarantee.",
    }
    print(json.dumps(report, indent=2))
    engine.dispose()
    temporary.cleanup()


if __name__ == "__main__":
    main()
