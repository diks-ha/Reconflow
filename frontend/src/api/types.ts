export type User = { id: string; email: string; full_name: string; roles: string[] }
export type Partner = { id: string; name: string; partner_type: string; created_at?: string }
export type ImportRecord = {
  id: string; partner_id: string; report_type: string; original_filename: string; file_size: number; file_format: string
  status: string; headers: string[]; row_count: number | null; mapping_version_id: string | null
  validation_report: Record<string, unknown> | null; error_message: string | null; created_at: string
}
export type MappingSuggestion = { source_column: string; canonical_field: string | null; confidence: number; explanation: string; uncertain: boolean }
export type MappingTemplate = { id: string; partner_id: string; report_type: string; name: string; latest_version: { id: string; version_number: number; mappings: { source_column: string; canonical_field: string | null }[] } | null }
export type ReconciliationResult = {
  id: string; run_id: string; order_id: string; status: string; expected_amount: string | null; received_amount: string | null
  difference: string | null; gst_tcs: string; income_tax_tds: string; findings: Finding[]; evidence: Evidence[]; explanation: string; created_at: string
}
export type Finding = { category: string; amount: string | null; explanation: string; confirmed: boolean; evidence: Evidence[] }
export type Evidence = { import_id?: string | null; row_number?: number | null; transaction_id?: string | null; source_type?: string; [key: string]: unknown }
export type Claim = {
  id: string; partner_id: string | null; partner: string; order_id: string; category: string; discrepancy_amount: string | null
  recovered_amount: string; status: string; reason: string; created_at: string; updated_at: string
  assigned_reviewer: { id: string; name: string } | null; evidence: { source_import_id: string | null; source_filename: string | null; transaction_id: string | null; source_row_number: number | null; details: Record<string, unknown> }[]
  notes: { id: string; user_id: string; note: string; created_at: string }[]
}
export type RateCard = {
  id: string; channel: string; courier_partner: string; min_weight: string; max_weight: string | null; forward_fee: string
  return_fee: string; cod_fee: string; fixed_charge: string; percentage_charge: string; effective_from: string; effective_to: string | null; source_note: string; is_active: boolean
}
export type ReturnRecord = {
  id: string; partner_id: string; order_id: string; return_id: string | null; tracking_id: string | null; return_status: string
  courier_partner: string | null; initiated_at: string | null; expected_warehouse_arrival: string | null; actual_warehouse_receipt: string | null
  warehouse_scan_status: string; days_overdue: number; overdue: boolean; evidence: { import_id: string; source_row_number: number; received_at: string | null; return_id: string | null; tracking_id: string | null }[]
}
