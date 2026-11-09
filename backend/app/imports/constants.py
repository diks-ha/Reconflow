from enum import StrEnum


class ReportType(StrEnum):
    ORDERS = "orders"
    MARKETPLACE_SETTLEMENT = "marketplace_settlement"
    COD_REMITTANCE = "cod_remittance"
    COURIER_FREIGHT_INVOICE = "courier_freight_invoice"
    WAREHOUSE_RETURN_RECEIPT = "warehouse_return_receipt"


class PartnerType(StrEnum):
    MARKETPLACE = "MARKETPLACE"
    COURIER = "COURIER"
    QUICK_COMMERCE = "QUICK_COMMERCE"
    WEBSITE = "WEBSITE"
    PAYMENT_PROVIDER = "PAYMENT_PROVIDER"
    WAREHOUSE = "WAREHOUSE"


STANDARD_FIELDS = {
    "order_id", "transaction_id", "tracking_id", "channel", "courier_partner", "payment_method",
    "order_value", "expected_amount", "received_amount", "freight_charge", "weight", "delivery_status",
    "settlement_date", "remittance_date", "return_status", "warehouse_received_date", "gst_tcs", "income_tax_tds",
    "settlement_due_date", "return_id", "return_initiated_date", "return_deadline",
}
NUMERIC_FIELDS = {
    "order_value", "expected_amount", "received_amount", "freight_charge", "weight", "gst_tcs", "income_tax_tds",
}
DATE_FIELDS = {"settlement_date", "remittance_date", "warehouse_received_date", "settlement_due_date", "return_initiated_date", "return_deadline"}
SUPPORTED_REPORT_TYPES = {value.value for value in ReportType}
SUPPORTED_PARTNER_TYPES = {value.value for value in PartnerType}

