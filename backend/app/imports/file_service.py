import hashlib
import csv
from uuid import uuid4
import zipfile
from pathlib import Path

import pandas as pd

from app.core.config import get_settings

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
PREVIEW_LIMIT = 20
CHUNK_SIZE = 10_000
MAX_XLSX_UNPACKED_BYTES = 500 * 1024 * 1024


class ImportFileError(ValueError):
    pass


def validate_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ImportFileError("Only CSV and XLSX files are supported")
    return extension


def inspect_file(path: Path, extension: str) -> tuple[list[str], list[dict[str, str]]]:
    try:
        if extension == ".xlsx":
            if not zipfile.is_zipfile(path):
                raise ImportFileError("The uploaded XLSX file is not a valid Excel workbook")
            with zipfile.ZipFile(path) as archive:
                unpacked_size = sum(entry.file_size for entry in archive.infolist())
                if unpacked_size > MAX_XLSX_UNPACKED_BYTES:
                    raise ImportFileError("The XLSX expands beyond the permitted processing limit")
        headers = _read_headers(path, extension)
        if not headers or any(not header for header in headers):
            raise ImportFileError("The report must contain non-empty column headers")
        if len({header.casefold() for header in headers}) != len(headers):
            raise ImportFileError("Duplicate column headers are not supported; rename duplicate columns and upload again")
        if extension == ".csv":
            frame = pd.read_csv(path, nrows=PREVIEW_LIMIT, dtype=str, keep_default_na=False, encoding="utf-8-sig", header=0, names=headers)
        else:
            with path.open("rb") as source:
                frame = pd.read_excel(source, nrows=PREVIEW_LIMIT, dtype=str, keep_default_na=False, engine="openpyxl", header=0, names=headers)
    except ImportFileError:
        raise
    except Exception as exc:
        raise ImportFileError(f"Unable to parse uploaded file: {exc.__class__.__name__}") from None

    frame.columns = headers
    rows = [{str(key): _cell(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]
    return headers, rows


def _read_headers(path: Path, extension: str) -> list[str]:
    try:
        if extension == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                values = next(csv.reader(source), [])
        else:
            from openpyxl import load_workbook

            with path.open("rb") as source:
                workbook = load_workbook(source, read_only=True, data_only=True)
                try:
                    values = next(workbook.worksheets[0].iter_rows(min_row=1, max_row=1, values_only=True), [])
                finally:
                    workbook.close()
    except ImportFileError:
        raise
    except Exception as exc:
        raise ImportFileError(f"Unable to read source headers: {exc.__class__.__name__}") from None
    return [str(value).strip() if value is not None else "" for value in values]


def _cell(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def save_upload_stream(upload, filename: str) -> tuple[Path, str, int, str]:
    """Persist an upload to private storage while hashing and enforcing the configured cap."""
    extension = validate_extension(filename)
    settings = get_settings()
    storage_dir = settings.upload_dir.resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    temporary = storage_dir / f".upload-{uuid4().hex}.tmp"
    digest = hashlib.sha256()
    size = 0
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    try:
        with temporary.open("wb") as destination:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise ImportFileError(f"File exceeds the {settings.max_upload_size_mb} MB upload limit")
                digest.update(chunk)
                destination.write(chunk)
        if size == 0:
            raise ImportFileError("Uploaded file is empty")
        if extension == ".csv":
            with temporary.open("rb") as source:
                prefix = source.read(4096)
            if b"\x00" in prefix:
                raise ImportFileError("The uploaded file does not appear to be a text CSV")
        final_path = storage_dir / f"{digest.hexdigest()}{extension}"
        return temporary, digest.hexdigest(), size, str(final_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def finalize_upload(temporary: Path, final_path: str) -> None:
    destination = Path(final_path)
    if destination.exists():
        temporary.unlink(missing_ok=True)
    else:
        temporary.replace(destination)


def validate_mapped_file(path: Path, extension: str, mappings: list[dict]) -> dict:
    """Check every mapped value and return compact counts plus a capped row-level error sample."""
    from app.imports.constants import DATE_FIELDS, NUMERIC_FIELDS

    field_stats: dict[str, dict[str, int]] = {
        mapping["canonical_field"]: {"missing": 0, "invalid": 0} for mapping in mappings if mapping.get("canonical_field")
    }
    source_to_target = {mapping["source_column"]: mapping["canonical_field"] for mapping in mappings if mapping.get("canonical_field")}
    errors: list[dict[str, object]] = []
    missing_sample: list[dict[str, object]] = []
    total = 0

    def check_frame(frame: pd.DataFrame) -> None:
        nonlocal total
        frame.columns = [str(c).strip() for c in frame.columns]
        total += len(frame)
        for source, target in source_to_target.items():
            series = frame[source].fillna("").astype(str).str.strip()
            missing = series.eq("")
            stats = field_stats[target]
            stats["missing"] += int(missing.sum())
            if len(missing_sample) < 20 and missing.any():
                for row_index in missing[missing].index[:20 - len(missing_sample)]:
                    missing_sample.append({
                        "row_number": int(row_index) + 2,
                        "source_column": source,
                        "canonical_field": target,
                    })
            if target in NUMERIC_FIELDS:
                valid = series.str.fullmatch(r"[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?|\.\d+)")
            elif target in DATE_FIELDS:
                valid = pd.to_datetime(series.where(~missing), errors="coerce", utc=True).notna()
            else:
                valid = pd.Series(True, index=series.index)
            invalid = ~missing & ~valid
            stats["invalid"] += int(invalid.sum())
            if len(errors) < 20 and invalid.any():
                for row_index in invalid[invalid].index[:20 - len(errors)]:
                    errors.append({
                        "row_number": int(row_index) + 2,
                        "source_column": source,
                        "canonical_field": target,
                    })

    try:
        if extension == ".csv":
            for chunk in pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", chunksize=CHUNK_SIZE):
                check_frame(chunk)
        else:
            with path.open("rb") as source:
                frame = pd.read_excel(source, dtype=str, keep_default_na=False, engine="openpyxl")
            check_frame(frame)
    except Exception as exc:
        raise ImportFileError(f"Unable to validate mapped file: {exc.__class__.__name__}") from None

    invalid_total = sum(stats["invalid"] for stats in field_stats.values())
    return {
        "valid": invalid_total == 0 and total > 0,
        "row_count": total,
        "mapped_fields": list(field_stats),
        "fields": field_stats,
        "invalid_value_count": invalid_total,
        "error_sample": errors,
        "missing_sample": missing_sample,
    }
