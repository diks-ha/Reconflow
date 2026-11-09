from io import BytesIO
from types import SimpleNamespace

import pytest

from app.ai.mapping import demo_suggestions
from app.imports.file_service import ImportFileError, inspect_file, save_upload_stream, validate_extension
from app.imports.service import (
    DuplicateImportError,
    approve_mapping,
    apply_mapping_template,
    create_partner,
    rollback_mapping,
    save_import,
    validate_import,
)
from app.models.user import User
from app.models.partner import Partner
from app.api.routes.imports import preview_import


def _upload(content: bytes, filename: str = "report.csv"):
    return SimpleNamespace(file=BytesIO(content), filename=filename)


def _settings(upload_dir, max_mb=2):
    return SimpleNamespace(upload_dir=upload_dir, max_upload_size_mb=max_mb)


def _import(db, monkeypatch, upload_dir, content=b"Order ID,Net Settlement\nORD-1,899\n", filename="report.csv"):
    import app.imports.file_service as file_service

    monkeypatch.setattr(file_service, "get_settings", lambda: _settings(upload_dir))
    user = db.query(User).filter_by(email="exec@example.com").one()
    partner = db.query(Partner).filter_by(name="Test Marketplace").one_or_none()
    if partner is None:
        partner = create_partner(db, "Test Marketplace", "MARKETPLACE")
    record = save_import(db, _upload(content, filename), filename, partner.id, "marketplace_settlement", user)
    return record, user, partner


def test_csv_upload_hash_header_and_twenty_row_preview(db, monkeypatch, writable_tmp_path):
    rows = "Order ID,Net Settlement\n" + "".join(f"ORD-{n},{n}.25\n" for n in range(25))
    record, _, _ = _import(db, monkeypatch, writable_tmp_path, rows.encode())
    assert record.status == "UPLOADED"
    assert record.file_format == "csv"
    assert record.headers == ["Order ID", "Net Settlement"]
    assert len(record.preview_rows) == 20
    assert len(record.file_hash) == 64


def test_preview_masks_customer_pii_but_keeps_original_source(db, monkeypatch, writable_tmp_path):
    content = b"Order ID,Customer Name,Customer Phone,Customer Email\nORD-1,Jane Doe,9876543210,jane@example.com\n"
    record, user, _ = _import(db, monkeypatch, writable_tmp_path, content)
    response = preview_import(record.id, user, db)
    assert response.rows[0]["Order ID"] == "ORD-1"
    assert response.rows[0]["Customer Name"] == "[REDACTED]"
    assert response.rows[0]["Customer Phone"] == "[REDACTED]"
    assert response.rows[0]["Customer Email"] == "[REDACTED]"
    assert record.preview_rows[0]["Customer Email"] == "jane@example.com"


def test_xlsx_upload_header_and_preview(db, monkeypatch, writable_tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from io import BytesIO

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Order ID", "Order Value"])
    sheet.append(["ORD-1", "1499"])
    content = BytesIO()
    workbook.save(content)
    record, _, _ = _import(db, monkeypatch, writable_tmp_path, content.getvalue(), "report.xlsx")
    assert record.headers == ["Order ID", "Order Value"]
    assert record.preview_rows == [{"Order ID": "ORD-1", "Order Value": "1499"}]


def test_duplicate_file_hash_is_rejected(db, monkeypatch, writable_tmp_path):
    content = b"Order ID,Net Settlement\nORD-1,899\n"
    record, user, partner = _import(db, monkeypatch, writable_tmp_path, content)
    import app.imports.file_service as file_service
    monkeypatch.setattr(file_service, "get_settings", lambda: _settings(writable_tmp_path))
    with pytest.raises(DuplicateImportError) as error:
        save_import(db, _upload(content), "duplicate.csv", partner.id, record.report_type, user)
    assert error.value.import_id == record.id


def test_file_validation_rejects_bad_extension_and_empty_or_duplicate_headers(writable_tmp_path):
    with pytest.raises(ImportFileError):
        validate_extension("report.xls")
    duplicate_header = writable_tmp_path / "duplicate.csv"
    duplicate_header.write_text("Order ID,order id\nA,B\n", encoding="utf-8")
    with pytest.raises(ImportFileError, match="Duplicate column headers"):
        inspect_file(duplicate_header, ".csv")
    with pytest.raises(ImportFileError):
        empty = writable_tmp_path / "empty.csv"
        empty.write_bytes(b"")
        inspect_file(empty, ".csv")
    malformed_xlsx = writable_tmp_path / "malformed.xlsx"
    malformed_xlsx.write_bytes(b"not an xlsx archive")
    with pytest.raises(ImportFileError, match="not a valid Excel workbook"):
        inspect_file(malformed_xlsx, ".xlsx")


def test_file_size_limit_is_enforced(monkeypatch, writable_tmp_path):
    import app.imports.file_service as file_service

    monkeypatch.setattr(file_service, "get_settings", lambda: _settings(writable_tmp_path, max_mb=1))
    with pytest.raises(ImportFileError, match="upload limit"):
        save_upload_stream(_upload(b"x" * (1024 * 1024 + 1)), "large.csv")


def test_ai_demo_suggestions_are_deterministic_and_not_saved():
    first = [item.model_dump() for item in demo_suggestions(["Net Settlement", "AWB Ref", "Mystery field"])]
    second = [item.model_dump() for item in demo_suggestions(["Net Settlement", "AWB Ref", "Mystery field"])]
    assert first == second
    assert first[0]["canonical_field"] == "received_amount"
    assert first[1]["canonical_field"] == "tracking_id"
    assert first[2]["uncertain"] is True


def test_mapping_approval_validation_and_mapping_versions(db, monkeypatch, writable_tmp_path):
    first, user, partner = _import(db, monkeypatch, writable_tmp_path)
    version_1 = approve_mapping(db, first, user, "Settlement report", [
        {"source_column": "Order ID", "canonical_field": "order_id"},
        {"source_column": "Net Settlement", "canonical_field": "received_amount"},
    ])
    assert first.status == "MAPPED"
    report = validate_import(db, first)
    assert report["valid"] is True
    assert report["row_count"] == 1
    assert first.status == "VALIDATED"

    second, _, _ = _import(db, monkeypatch, writable_tmp_path, b"Order ID,Net Settlement\nORD-2,bad\nORD-3,\n", "report2.csv")
    apply_mapping_template(db, second, version_1.id)
    report = validate_import(db, second)
    assert report["valid"] is False
    assert report["fields"]["received_amount"]["invalid"] == 1
    assert report["fields"]["received_amount"]["missing"] == 1
    assert report["error_sample"][0]["row_number"] == 2
    assert "value" not in report["error_sample"][0]
    assert report["missing_sample"][0]["row_number"] == 3
    assert second.status == "INVALID"

    version_2 = approve_mapping(db, second, user, "Settlement report", [
        {"source_column": "Order ID", "canonical_field": "order_id"},
        {"source_column": "Net Settlement", "canonical_field": "expected_amount"},
    ])
    rollback = rollback_mapping(db, version_1.template_id, version_1.id, user)
    assert version_2.version_number == 2
    assert rollback.version_number == 3
    assert rollback.parent_version_id == version_1.id
    assert rollback.mappings == version_1.mappings
    assert partner.id


def test_mapping_approval_rejects_unknown_or_duplicate_fields(db, monkeypatch, writable_tmp_path):
    record, user, _ = _import(db, monkeypatch, writable_tmp_path)
    with pytest.raises(ValueError, match="Unsupported standardized field"):
        approve_mapping(db, record, user, "Bad mapping", [{"source_column": "Order ID", "canonical_field": "customer_phone"}])
    with pytest.raises(ValueError, match="More than one source column maps"):
        approve_mapping(db, record, user, "Bad mapping", [
            {"source_column": "Order ID", "canonical_field": "order_id"},
            {"source_column": "Net Settlement", "canonical_field": "order_id"},
        ])

