import json
import re

import httpx

from app.core.config import get_settings
from app.imports.constants import STANDARD_FIELDS
from app.schemas.imports import SuggestionItem

DEMO_MATCHES: dict[str, tuple[str, float, str]] = {
    "order id": ("order_id", 98, "The header identifies the order reference."),
    "order no": ("order_id", 96, "The header is a common label for an order identifier."),
    "transaction id": ("transaction_id", 98, "The header identifies a payment or settlement transaction."),
    "awb ref": ("tracking_id", 94, "AWB is a shipment airway-bill or tracking reference."),
    "awb number": ("tracking_id", 96, "AWB is a shipment airway-bill or tracking reference."),
    "tracking id": ("tracking_id", 98, "The header identifies a shipment tracking reference."),
    "net settlement": ("received_amount", 96, "Net settlement is the amount transferred after deductions."),
    "settlement amount": ("received_amount", 91, "The header describes an amount settled to the business."),
    "amount received": ("received_amount", 97, "The header directly describes the received amount."),
    "expected amount": ("expected_amount", 98, "The header directly describes the expected amount."),
    "order value": ("order_value", 98, "The header directly describes the order value."),
    "cod remittance": ("received_amount", 91, "The header describes money remitted for COD orders."),
    "freight charge": ("freight_charge", 97, "The header describes billed shipping or freight."),
    "shipping fee": ("freight_charge", 87, "The header likely describes a shipping charge."),
    "weight": ("weight", 94, "The header describes parcel weight."),
    "delivery status": ("delivery_status", 96, "The header describes delivery state."),
    "payment method": ("payment_method", 97, "The header describes how the order was paid."),
    "settlement date": ("settlement_date", 98, "The header describes settlement timing."),
    "remittance date": ("remittance_date", 98, "The header describes COD remittance timing."),
    "return status": ("return_status", 97, "The header describes return state."),
    "warehouse received date": ("warehouse_received_date", 97, "The header describes warehouse receipt timing."),
    "gst tcs": ("gst_tcs", 98, "The header explicitly identifies GST TCS."),
    "income tax tds": ("income_tax_tds", 98, "The header explicitly identifies income-tax TDS."),
    "channel": ("channel", 90, "The header identifies the sales channel."),
    "courier partner": ("courier_partner", 93, "The header identifies the courier partner."),
}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def demo_suggestions(headers: list[str]) -> list[SuggestionItem]:
    suggestions: list[SuggestionItem] = []
    for header in headers:
        normalized = _normalize(header)
        match = DEMO_MATCHES.get(normalized)
        if match is None:
            # Token matching stays conservative: generic words such as "amount" remain uncertain.
            candidates = [entry for key, entry in DEMO_MATCHES.items() if key in normalized]
            if len(candidates) == 1 and len(normalized.split()) > 1:
                match = candidates[0]
        if match:
            canonical, confidence, explanation = match
            uncertain = confidence < 75
        else:
            canonical, confidence = None, 0
            explanation = "No reliable deterministic match was found; choose a field manually."
            uncertain = True
        suggestions.append(SuggestionItem(
            source_column=header,
            canonical_field=canonical,
            confidence=confidence,
            explanation=explanation,
            uncertain=uncertain,
        ))
    return suggestions


async def suggest_mappings(headers: list[str]) -> tuple[str, str, list[SuggestionItem]]:
    settings = get_settings()
    if not settings.llm_api_key:
        return "demo", "Demo mode: deterministic header rules were used; no LLM request was made.", demo_suggestions(headers)

    system_prompt = (
        "You suggest mappings from file column headers to standardized fields. "
        "Do not calculate, alter, approve, or infer financial values. Return one suggestion for each supplied header. "
        "Return JSON only with shape {\"suggestions\":[{\"source_column\":string,\"canonical_field\":string|null,"
        "\"confidence\":number,\"explanation\":string,\"uncertain\":boolean}]}. Confidence is 0 to 100. "
        "Use null and uncertain=true when evidence is weak. Allowed canonical fields: "
        + ", ".join(sorted(STANDARD_FIELDS))
        + "."
    )
    request_body = {
        "model": settings.llm_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({"headers": headers}, ensure_ascii=False)},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"},
                json=request_body,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        payload = json.loads(content)
        entries = payload["suggestions"]
        by_header = {item["source_column"]: item for item in entries}
        if set(by_header) != set(headers) or len(entries) != len(headers):
            raise ValueError("LLM suggestions did not match the uploaded headers")
        suggestions: list[SuggestionItem] = []
        seen_targets: set[str] = set()
        for header in headers:
            item = by_header[header]
            target = item.get("canonical_field")
            if target is not None and target not in STANDARD_FIELDS:
                raise ValueError("LLM returned an unsupported standardized field")
            confidence = float(item["confidence"])
            if target in seen_targets:
                item["uncertain"] = True
                item["explanation"] += " Multiple source columns received this field; review the mapping."
            if target:
                seen_targets.add(target)
            suggestions.append(SuggestionItem(
                source_column=header,
                canonical_field=target,
                confidence=confidence,
                explanation=str(item["explanation"])[:500],
                uncertain=bool(item["uncertain"]) or confidence < 75 or target is None,
            ))
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LLM mapping request failed or returned invalid structured data ({exc.__class__.__name__})") from None
    return "llm", "LLM suggestions only; review and explicitly approve before saving.", suggestions

