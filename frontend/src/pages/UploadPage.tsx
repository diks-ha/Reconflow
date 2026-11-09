import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, FileSpreadsheet, RefreshCw, UploadCloud } from 'lucide-react'
import { api, errorMessage } from '../api/client'
import type { ImportRecord, Partner } from '../api/types'
import { Badge, Button, DataTable, EmptyState, ErrorState, Field, PageHeader, Panel, SearchBox, Select, Spinner, useToast } from '../components/UI'

const reportTypes = [
  ['orders', 'Orders'], ['marketplace_settlement', 'Marketplace settlement'], ['cod_remittance', 'COD remittance'],
  ['courier_freight_invoice', 'Courier freight invoice'], ['warehouse_return_receipt', 'Warehouse return receipt'],
]
export function UploadPage() {
  const [partners, setPartners] = useState<Partner[]>([]); const [imports, setImports] = useState<ImportRecord[]>([]); const [partnerId, setPartnerId] = useState(''); const [reportType, setReportType] = useState('orders'); const [file, setFile] = useState<File | null>(null); const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [fileError, setFileError] = useState(''); const [historySearch, setHistorySearch] = useState(''); const [historyStatus, setHistoryStatus] = useState('')
  const navigate = useNavigate(); const toast = useToast()
  const visibleImports = imports.filter((item) => (!historyStatus || item.status === historyStatus) && (!historySearch || `${item.original_filename} ${item.report_type} ${partners.find((p) => p.id === item.partner_id)?.name || ''}`.toLowerCase().includes(historySearch.toLowerCase())))
  async function load() { setLoading(true); setError(''); try { const [p, i] = await Promise.all([api.get<Partner[]>('/partners'), api.get<ImportRecord[]>('/imports?limit=100')]); setPartners(p.data); setImports(i.data); if (!partnerId && p.data.length) setPartnerId(p.data[0].id) } catch (problem) { setError(errorMessage(problem)) } finally { setLoading(false) } }
  useEffect(() => { void load() }, [])
  function chooseFile(next: File | null) { setFileError(''); if (next && !/\.(csv|xlsx)$/i.test(next.name)) { setFile(null); setFileError('Choose a CSV or XLSX file.'); return } setFile(next) }
  async function submit(event: FormEvent) { event.preventDefault(); setFileError(''); if (!file) { setFileError('Select a CSV or XLSX file to upload.'); return } if (!partnerId) { setFileError('Choose the partner that supplied this file.'); return } const form = new FormData(); form.append('file', file); form.append('partner_id', partnerId); form.append('report_type', reportType); setBusy(true); try { const { data } = await api.post<ImportRecord>('/imports/upload', form); toast('File uploaded. Review its columns to continue.'); navigate(`/imports/${data.id}/mapping`) } catch (problem) { setFileError(errorMessage(problem)) } finally { setBusy(false) } }
  const statusTone = (status: string) => status === 'PROCESSED' ? 'green' as const : status === 'FAILED' ? 'red' as const : status === 'VALIDATED' ? 'blue' as const : 'amber' as const
  return <><PageHeader eyebrow="DATA INTAKE" title="File uploads" description="Bring partner exports into ReconFlow and review each file before it enters reconciliation." action={<Button variant="secondary" onClick={() => void load()}><RefreshCw size={15} /> Refresh history</Button>} />
    <div className="upload-layout"><Panel><div className="panel-heading"><div><h2>Upload partner file</h2><p>CSV or Excel workbook · mapping is reviewed before processing</p></div><div className="upload-heading-icon"><UploadCloud size={19} /></div></div>
      <form className="upload-form" onSubmit={submit} noValidate><Field label="Partner"><Select required value={partnerId} onChange={(e) => setPartnerId(e.target.value)}><option value="">Select partner</option>{partners.map((partner) => <option key={partner.id} value={partner.id}>{partner.name} · {partner.partner_type.replaceAll('_', ' ')}</option>)}</Select></Field>
        <Field label="Report type"><Select value={reportType} onChange={(e) => setReportType(e.target.value)}>{reportTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field>
        <label className={`drop-zone ${file ? 'drop-zone-selected' : ''}`} onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); chooseFile(e.dataTransfer.files[0] || null) }}><input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(e) => chooseFile(e.target.files?.[0] || null)} /><div className="drop-icon">{file ? <FileSpreadsheet size={21} /> : <UploadCloud size={22} />}</div><b>{file?.name || 'Drop your file here or browse'}</b><span>{file ? `${(file.size / 1024).toFixed(0)} KB · ${file.name.split('.').pop()?.toUpperCase()}` : 'Supported formats: CSV, XLSX'}</span></label>
        {fileError && <div className="form-alert">{fileError}</div>}<Button type="submit" disabled={busy || !partners.length} className="full-button">{busy ? <Spinner label="Uploading file" /> : <>Upload and map columns <ArrowRight size={16} /></>}</Button>
        {!loading && !partners.length && <p className="field-error">No partners are configured. Ask a Finance Co-founder to add a partner first.</p>}
      </form>
      <div className="upload-steps"><div><span>1</span><b>Upload</b><small>File is checked and fingerprinted</small></div><div><span>2</span><b>Map</b><small>Review and approve each column</small></div><div><span>3</span><b>Process</b><small>Validated data enters reconciliation</small></div></div>
    </Panel><Panel className="upload-info"><div className="eyebrow">SAFE BY DESIGN</div><h2>Review before processing</h2><p>ReconFlow keeps the original file, previews sample rows and flags missing or invalid values. AI can suggest a column mapping, but it is never saved or approved automatically.</p><div className="info-stat"><FileSpreadsheet size={17} /><span><b>{imports.length}</b> recent imports</span></div></Panel></div>
    <div className="filter-bar upload-history"><SearchBox value={historySearch} onChange={setHistorySearch} placeholder="Search files, partners or report type" /><div className="filter-select"><Select value={historyStatus} onChange={(e) => setHistoryStatus(e.target.value)}><option value="">All statuses</option>{['UPLOADED','MAPPED','INVALID','VALIDATED','PROCESSED','FAILED'].map((item) => <option value={item} key={item}>{item.replaceAll('_', ' ')}</option>)}</Select></div><span className="results-count">{visibleImports.length} imports</span></div>
    <Panel padding={false} className="history-panel"><div className="panel-heading panel-heading-pad"><div><h2>Import history</h2><p>Review file processing and mapping status</p></div></div>{error ? <div className="panel-padding"><ErrorState message={error} retry={() => void load()} /></div> : loading ? <div className="panel-padding"><div className="skeleton-row">{[0,1,2,3].map((n) => <div className="skeleton h-4" key={n} />)}</div></div> : <DataTable rows={visibleImports} keyOf={(item) => item.id} emptyTitle="No files match these filters" emptyDescription="Choose a partner report above to create your first import or change your filters." columns={[
      { title: 'File', render: (item) => <div className="file-cell"><span className="file-type-icon"><FileSpreadsheet size={16} /></span><div><b>{item.original_filename}</b><small>{item.file_format.toUpperCase()} · {(item.file_size / 1024).toFixed(0)} KB</small></div></div> },
      { title: 'Partner', render: (item) => partners.find((p) => p.id === item.partner_id)?.name || 'Partner' },
      { title: 'Report type', render: (item) => item.report_type.replaceAll('_', ' ') },
      { title: 'Rows', render: (item) => item.row_count ?? '—' },
      { title: 'Status', render: (item) => <Badge tone={statusTone(item.status)}>{item.status.replaceAll('_', ' ')}</Badge> },
      { title: 'Uploaded', render: (item) => new Date(item.created_at).toLocaleString() },
      { title: '', render: (item) => ['UPLOADED', 'MAPPED', 'INVALID', 'VALIDATED'].includes(item.status) ? <Link className="table-link" to={`/imports/${item.id}/mapping`}>Continue <ArrowRight size={13} /></Link> : <span className="muted">{item.status === 'PROCESSED' ? 'Ready for reconciliation' : item.error_message || '—'}</span> },
    ]} />}</Panel>
  </>
}
