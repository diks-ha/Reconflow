from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.models.finance import CodRemittance, FreightInvoice, Order, RateCard, ReturnRecord, Settlement, WarehouseReceipt
from app.models.import_record import ImportRecord
from app.models.mapping import MappingVersion
from app.models.partner import Partner
from app.imports.file_service import CHUNK_SIZE


class ImportProcessingError(ValueError):
    pass


def _as_decimal(value: object) -> Decimal | None:
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        raise ImportProcessingError("Invalid numeric value in mapped source data") from None


def _as_date(value: object) -> date | None:
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    # Most partner exports use ISO dates; avoid pandas' scalar parser in the hot row loop.
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        raise ImportProcessingError("Invalid date value in mapped source data") from None
    return parsed.date()


def process_validated_import(db: Session, import_id: UUID) -> dict:
    record = db.get(ImportRecord, import_id)
    if record is None:
        raise LookupError("Import not found")
    if record.status != "VALIDATED":
        raise ImportProcessingError("Only imports with VALIDATED status can be processed")
    if not record.mapping_version_id:
        raise ImportProcessingError("An approved mapping is required")
    version = db.get(MappingVersion, record.mapping_version_id)
    partner = db.get(Partner, record.partner_id)
    if not Path(record.storage_key).is_file():
        raise ImportProcessingError("Original import file is unavailable")

    if record.file_format not in {"csv", "xlsx"}:
        raise ImportProcessingError("Unsupported stored import format")

    targets = {item["canonical_field"]: item["source_column"] for item in version.mappings if item.get("canonical_field")}
    required_by_type = {
        "orders": {"order_id"},
        "marketplace_settlement": {"order_id", "received_amount"},
        "cod_remittance": {"order_id", "received_amount"},
        "courier_freight_invoice": {"order_id", "freight_charge"},
        "warehouse_return_receipt": set(),
    }
    required = required_by_type.get(record.report_type, set())
    absent = required - set(targets)
    if absent:
        raise ImportProcessingError("Mapping is missing required fields: " + ", ".join(sorted(absent)))

    inserted = 0

    def row_batches():
        """Yield bounded source row batches; CSV stays streaming at the import layer."""
        try:
            if record.file_format == "csv":
                frames = pd.read_csv(record.storage_key, dtype=str, keep_default_na=False,
                                     encoding="utf-8-sig", chunksize=CHUNK_SIZE)
            else:
                full_frame = pd.read_excel(record.storage_key, dtype=str, keep_default_na=False, engine="openpyxl")
                frames = (full_frame.iloc[start:start + CHUNK_SIZE] for start in range(0, len(full_frame), CHUNK_SIZE))
            row_number = 2
            for frame in frames:
                values = frame.to_dict(orient="records")
                yield [(row_number + index, raw) for index, raw in enumerate(values)]
                row_number += len(values)
        except ImportProcessingError:
            raise
        except Exception as exc:
            raise ImportProcessingError(f"Unable to read original import ({exc.__class__.__name__})") from None

    def make_normalized(row_number: int, raw: dict) -> dict:
        normalized = {field: (str(raw.get(source, "")).strip() or None) for field, source in targets.items()}
        normalized["_raw"] = {str(key): (str(value) if value is not None else "") for key, value in raw.items()}
        normalized["_row_number"] = row_number
        return normalized

    try:
        with db.begin_nested():
            record.status = "PROCESSING"
            db.flush()
            for source_batch in row_batches():
                table_rows: list[dict] = []
                return_rows: list[dict] = []
                for row_no, raw in source_batch:
                    row = make_normalized(row_no, raw)
                    order_id = row.get("order_id")
                    raw_source = row["_raw"]
                    if record.report_type == "orders":
                        if not order_id:
                            raise ImportProcessingError(f"Missing order_id at source row {row_no}")
                        channel = row.get("channel") or partner.name
                        table_rows.append({
                            "id": uuid4(), "order_id": order_id, "partner_id": record.partner_id, "channel": channel,
                            "payment_method": row.get("payment_method"), "delivery_status": row.get("delivery_status"),
                            "order_value": _as_decimal(row.get("order_value")), "expected_amount": _as_decimal(row.get("expected_amount")),
                            "settlement_due_date": _as_date(row.get("settlement_due_date")),
                            "payment_eligible": (row.get("delivery_status") or "").casefold() == "delivered",
                            "return_status": row.get("return_status"), "return_id": row.get("return_id"),
                            "return_deadline": _as_date(row.get("return_deadline")), "tracking_id": row.get("tracking_id"),
                            "raw_source": raw_source, "source_import_id": record.id, "source_row_number": row_no,
                        })
                        if row.get("return_status"):
                            return_rows.append({
                                "id": uuid4(), "partner_id": record.partner_id, "order_id": order_id,
                                "return_id": row.get("return_id"), "return_status": row["return_status"],
                                "courier_partner": row.get("courier_partner"), "tracking_id": row.get("tracking_id"),
                                "initiated_at": _as_date(row.get("return_initiated_date")),
                                "deadline": _as_date(row.get("return_deadline")), "source_import_id": record.id,
                                "source_row_number": row_no, "raw_source": raw_source,
                            })
                    elif record.report_type in {"marketplace_settlement", "cod_remittance"}:
                        if not order_id:
                            raise ImportProcessingError(f"Missing order_id at source row {row_no}")
                        amount = _as_decimal(row.get("received_amount"))
                        if amount is None:
                            raise ImportProcessingError(f"Missing received_amount at source row {row_no}")
                        common = {"id": uuid4(), "partner_id": record.partner_id, "order_id": order_id,
                                  "transaction_id": row.get("transaction_id"), "amount": amount,
                                  "source_import_id": record.id, "source_row_number": row_no, "raw_source": raw_source}
                        if record.report_type == "marketplace_settlement":
                            common.update({"gst_tcs": _as_decimal(row.get("gst_tcs")) or Decimal("0.00"),
                                           "income_tax_tds": _as_decimal(row.get("income_tax_tds")) or Decimal("0.00"),
                                           "settled_at": _as_date(row.get("settlement_date"))})
                        else:
                            common["remitted_at"] = _as_date(row.get("remittance_date"))
                        table_rows.append(common)
                    elif record.report_type == "courier_freight_invoice":
                        if not order_id:
                            raise ImportProcessingError(f"Missing order_id at source row {row_no}")
                        charge = _as_decimal(row.get("freight_charge"))
                        if charge is None:
                            raise ImportProcessingError(f"Missing freight_charge at source row {row_no}")
                        table_rows.append({
                            "id": uuid4(), "partner_id": record.partner_id, "order_id": order_id,
                            "transaction_id": row.get("transaction_id"), "tracking_id": row.get("tracking_id"),
                            "courier_partner": row.get("courier_partner") or partner.name, "billed_charge": charge,
                            "weight": _as_decimal(row.get("weight")), "source_import_id": record.id,
                            "source_row_number": row_no, "raw_source": raw_source,
                        })
                    elif record.report_type == "warehouse_return_receipt":
                        return_id, tracking_id = row.get("return_id"), row.get("tracking_id")
                        if not order_id and not return_id and not tracking_id:
                            raise ImportProcessingError(f"No order, return, or tracking identifier at source row {row_no}")
                        table_rows.append({
                            "id": uuid4(), "order_id": order_id or "", "return_id": return_id,
                            "tracking_id": tracking_id, "received_at": _as_date(row.get("warehouse_received_date")),
                            "source_import_id": record.id, "source_row_number": row_no, "raw_source": raw_source,
                        })
                model = {
                    "orders": Order, "marketplace_settlement": Settlement, "cod_remittance": CodRemittance,
                    "courier_freight_invoice": FreightInvoice, "warehouse_return_receipt": WarehouseReceipt,
                }.get(record.report_type)
                if model and table_rows:
                    db.execute(insert(model), table_rows)
                if return_rows:
                    db.execute(insert(ReturnRecord), return_rows)
                inserted += len(source_batch)
            record.status = "PROCESSED"
            record.error_message = None
            db.flush()
        db.commit()
    except Exception:
        db.rollback()
        record = db.get(ImportRecord, import_id)
        if record:
            record.status = "FAILED"
            record.error_message = "Import processing failed; review the source data and uniqueness constraints."
            db.commit()
        raise
    return {"import_id": str(import_id), "status": "PROCESSED", "rows_processed": inserted}


def load_reconciliation_inputs(db: Session, import_ids: list[UUID], as_of: date, threshold: Decimal):
    from app.reconciliation.engine import (
        FreightInput, OrderInput, PaymentInput, RateInput, ReconciliationInput, WarehouseReceiptInput,
    )

    records = list(db.scalars(select(ImportRecord).where(ImportRecord.id.in_(import_ids))))
    if len(records) != len(set(import_ids)):
        raise LookupError("One or more imports were not found")
    if any(item.status != "PROCESSED" for item in records):
        raise ImportProcessingError("All selected imports must be processed before reconciliation")
    ids = set(import_ids)
    orders_db = list(db.scalars(select(Order).where(Order.source_import_id.in_(ids))))
    order_by_id = {item.order_id: item for item in orders_db}
    orders = [OrderInput(
        order_id=item.order_id, expected_amount=item.expected_amount, payment_method=item.payment_method,
        order_value=item.order_value, channel=item.channel, delivery_status=item.delivery_status,
        settlement_due_date=item.settlement_due_date, payment_eligible=item.payment_eligible,
        return_status=item.return_status, return_id=item.return_id, return_deadline=item.return_deadline,
        tracking_id=item.tracking_id, source_import_id=str(item.source_import_id),
        source_row_number=item.source_row_number, raw_source=item.raw_source, partner_id=str(item.partner_id),
    ) for item in orders_db]
    settlements = [PaymentInput(
        order_id=item.order_id, amount=item.amount, transaction_id=item.transaction_id, partner_id=str(item.partner_id),
        gst_tcs=item.gst_tcs, income_tax_tds=item.income_tax_tds, source_import_id=str(item.source_import_id),
        source_row_number=item.source_row_number, source_type="settlement",
    ) for item in db.scalars(select(Settlement).where(Settlement.source_import_id.in_(ids)))]
    cods = [PaymentInput(
        order_id=item.order_id, amount=item.amount, transaction_id=item.transaction_id, partner_id=str(item.partner_id),
        source_import_id=str(item.source_import_id), source_row_number=item.source_row_number, source_type="cod_remittance",
    ) for item in db.scalars(select(CodRemittance).where(CodRemittance.source_import_id.in_(ids)))]
    freight = [FreightInput(
        order_id=item.order_id, billed_charge=item.billed_charge, channel=order_by_id.get(item.order_id).channel if order_by_id.get(item.order_id) else None,
        courier_partner=item.courier_partner, weight=item.weight, tracking_id=item.tracking_id, transaction_id=item.transaction_id,
        partner_id=str(item.partner_id),
        source_import_id=str(item.source_import_id), source_row_number=item.source_row_number,
    ) for item in db.scalars(select(FreightInvoice).where(FreightInvoice.source_import_id.in_(ids)))]
    receipts = [WarehouseReceiptInput(
        order_id=item.order_id, received_at=item.received_at, return_id=item.return_id, tracking_id=item.tracking_id,
        source_import_id=str(item.source_import_id), source_row_number=item.source_row_number,
    ) for item in db.scalars(select(WarehouseReceipt).where(WarehouseReceipt.source_import_id.in_(ids)))]
    cards = [RateInput(
        channel=item.channel, courier_partner=item.courier_partner, min_weight=item.min_weight, max_weight=item.max_weight,
        forward_fee=item.forward_fee, return_fee=item.return_fee, cod_fee=item.cod_fee, fixed_charge=item.fixed_charge,
        percentage_charge=item.percentage_charge, effective_from=item.effective_from, effective_to=item.effective_to,
        is_active=item.is_active,
    ) for item in db.scalars(select(RateCard).where(RateCard.is_active.is_(True)))]
    return ReconciliationInput(orders, settlements, cods, freight, receipts, cards, as_of, threshold)
