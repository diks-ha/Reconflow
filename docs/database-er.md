# ReconFlow Database ER Diagram

```mermaid
erDiagram
  USERS ||--o{ USER_ROLES : has
  ROLES ||--o{ USER_ROLES : grants
  USERS ||--o{ IMPORTS : uploads
  PARTNERS ||--o{ IMPORTS : scopes
  PARTNERS ||--o{ ORDERS : owns
  PARTNERS ||--o{ SETTLEMENTS : pays
  PARTNERS ||--o{ COD_REMITTANCES : remits
  PARTNERS ||--o{ FREIGHT_INVOICES : bills
  PARTNERS ||--o{ RETURNS : tracks
  PARTNERS ||--o{ RATE_CARDS : rates
  MAPPING_TEMPLATES ||--o{ MAPPING_VERSIONS : versions
  MAPPING_VERSIONS ||--o{ COLUMN_MAPPINGS : contains
  IMPORTS ||--o{ ORDERS : source
  IMPORTS ||--o{ SETTLEMENTS : source
  IMPORTS ||--o{ COD_REMITTANCES : source
  IMPORTS ||--o{ FREIGHT_INVOICES : source
  IMPORTS ||--o{ WAREHOUSE_RECEIPTS : source
  IMPORTS ||--o{ RETURNS : source
  USERS ||--o{ RECONCILIATION_RUNS : starts
  RECONCILIATION_RUNS ||--o{ RECONCILIATION_RESULTS : produces
  RECONCILIATION_RESULTS ||--o{ CLAIMS : evidence_for
  CLAIMS ||--o{ CLAIM_EVIDENCE : supported_by
  CLAIMS ||--o{ CLAIM_NOTES : discussed_in
  RATE_CARDS ||--o{ RATE_CARD_HISTORY : snapshots
  USERS ||--o{ AUDIT_LOGS : acts

  USERS { uuid id PK; string email UK; string full_name; string password_hash; bool is_active }
  ROLES { int id PK; string name UK; string description }
  USER_ROLES { int id PK; uuid user_id FK; int role_id FK }
  PARTNERS { uuid id PK; string name UK; string partner_type }
  IMPORTS { uuid id PK; uuid uploaded_by FK; uuid partner_id FK; string report_type; string file_hash UK; string status; json headers; json validation_report }
  MAPPING_TEMPLATES { uuid id PK; uuid partner_id FK; string report_type; string name }
  MAPPING_VERSIONS { uuid id PK; uuid template_id FK; int version_number; uuid parent_version_id FK; json mappings }
  COLUMN_MAPPINGS { int id PK; uuid mapping_version_id FK; string source_column; string canonical_field }
  ORDERS { uuid id PK; string order_id; uuid partner_id FK; numeric expected_amount; uuid source_import_id FK; int source_row_number }
  SETTLEMENTS { uuid id PK; string order_id; numeric amount; numeric gst_tcs; numeric income_tax_tds; uuid source_import_id FK }
  COD_REMITTANCES { uuid id PK; string order_id; numeric amount; uuid source_import_id FK }
  FREIGHT_INVOICES { uuid id PK; string order_id; numeric billed_charge; numeric weight; uuid source_import_id FK }
  WAREHOUSE_RECEIPTS { uuid id PK; string order_id; string return_id; string tracking_id; date received_at; uuid source_import_id FK }
  RETURNS { uuid id PK; string order_id; string return_id; string return_status; date deadline; uuid source_import_id FK }
  RATE_CARDS { uuid id PK; string channel; string courier_partner; numeric forward_fee; numeric return_fee; numeric cod_fee; date effective_from; date effective_to }
  RATE_CARD_HISTORY { uuid id PK; uuid rate_card_id FK; int version_number; json snapshot }
  RECONCILIATION_RUNS { uuid id PK; uuid created_by FK; numeric threshold; json summary }
  RECONCILIATION_RESULTS { uuid id PK; uuid run_id FK; uuid partner_id FK; string order_id; string status; numeric expected_amount; numeric received_amount; numeric difference; json findings }
  CLAIMS { uuid id PK; uuid reconciliation_result_id FK; uuid partner_id FK; string order_id; string category; numeric amount; numeric recovered_amount; string status }
  CLAIM_EVIDENCE { uuid id PK; uuid claim_id FK; uuid source_import_id FK; string transaction_id; int source_row_number }
  CLAIM_NOTES { uuid id PK; uuid claim_id FK; uuid user_id FK; string note }
  AUDIT_LOGS { uuid id PK; uuid user_id FK; string action; string entity_type; string entity_id; json before_json; json after_json }
```

Money columns use PostgreSQL `NUMERIC` and Python `Decimal`. Duplicate source rows/transactions and duplicate claim category per order are constrained in the database. JSON columns retain source data, mappings, validation reports, findings, and audit snapshots. This diagram summarizes the main model relationships.
