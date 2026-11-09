import { createContext, useContext, useMemo, useState, type FormEvent, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'
import { AlertCircle, CheckCircle2, ChevronLeft, ChevronRight, Info, LoaderCircle, Search, X } from 'lucide-react'

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="page-header"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{action && <div className="page-action">{action}</div>}</div>
}
export function Panel({ children, className = '', padding = true }: { children: ReactNode; className?: string; padding?: boolean }) { return <section className={`panel ${padding ? 'panel-padding' : ''} ${className}`}>{children}</section> }
export function Button({ children, variant = 'primary', className = '', disabled, type = 'button', onClick }: { children: ReactNode; variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; className?: string; disabled?: boolean; type?: 'button' | 'submit'; onClick?: () => void }) {
  return <button className={`btn btn-${variant} ${className}`} disabled={disabled} type={type} onClick={onClick}>{children}</button>
}
export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: ReactNode }) { return <label className="field"><span className="field-label">{label}</span>{children}{hint && <small className="field-hint">{hint}</small>}{error && <small className="field-error">{error}</small>}</label> }
export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) { return <input {...props} className={`input ${props.className || ''}`} /> }
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) { return <select {...props} className={`input select ${props.className || ''}`} /> }
export function Badge({ children, tone = 'slate' }: { children: ReactNode; tone?: 'slate' | 'green' | 'amber' | 'red' | 'blue' }) { return <span className={`badge badge-${tone}`}>{children}</span> }
export function Skeleton({ className = '' }: { className?: string }) { return <div className={`skeleton ${className}`} /> }
export function LoadingRows({ rows = 5, columns = 4 }: { rows?: number; columns?: number }) { return <div className="space-y-3">{Array.from({ length: rows }, (_, i) => <div className="skeleton-row" key={i}>{Array.from({ length: columns }, (_, j) => <Skeleton key={j} className="h-4" />)}</div>)}</div> }
export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) { return <div className="empty-state"><div className="empty-mark"><Info size={19} /></div><h3>{title}</h3><p>{description}</p>{action}</div> }
export function ErrorState({ message, retry }: { message: string; retry?: () => void }) { return <div className="error-state"><AlertCircle size={18} /><span>{message}</span>{retry && <button onClick={retry}>Try again</button>}</div> }
export function SearchBox({ value, onChange, placeholder = 'Search...' }: { value: string; onChange: (value: string) => void; placeholder?: string }) { return <div className="search-box"><Search size={16} /><input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} /></div> }

export function DataTable<T>({ columns, rows, keyOf, emptyTitle = 'Nothing here yet', emptyDescription = 'Records will appear here when data is available.' }: { columns: { title: string; render: (row: T) => ReactNode; className?: string }[]; rows: T[]; keyOf: (row: T) => string; emptyTitle?: string; emptyDescription?: string }) {
  const [page, setPage] = useState(1); const pageSize = 8; const pageCount = Math.max(1, Math.ceil(rows.length / pageSize)); const safePage = Math.min(page, pageCount); const visible = rows.slice((safePage - 1) * pageSize, safePage * pageSize)
  return rows.length === 0 ? <EmptyState title={emptyTitle} description={emptyDescription} /> : <>
    <div className="table-wrap"><table className="data-table"><thead><tr>{columns.map((column) => <th className={column.className} key={column.title}>{column.title}</th>)}</tr></thead><tbody>{visible.map((row) => <tr key={keyOf(row)}>{columns.map((column) => <td className={column.className} key={column.title}>{column.render(row)}</td>)}</tr>)}</tbody></table></div>
    <div className="table-footer"><span>{(safePage - 1) * pageSize + 1}–{Math.min(safePage * pageSize, rows.length)} of {rows.length}</span><div className="pager"><button aria-label="Previous page" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}><ChevronLeft size={16} /></button><span>{safePage} / {pageCount}</span><button aria-label="Next page" disabled={safePage >= pageCount} onClick={() => setPage(safePage + 1)}><ChevronRight size={16} /></button></div></div>
  </>
}

type ToastItem = { id: number; message: string; kind: 'success' | 'error' | 'info' }
type ToastContextValue = { toast: (message: string, kind?: ToastItem['kind']) => void }
const ToastContext = createContext<ToastContextValue | null>(null)
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const toast = (message: string, kind: ToastItem['kind'] = 'success') => { const id = Date.now() + Math.random(); setItems((current) => [...current, { id, message, kind }]); window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 4200) }
  const context = useMemo(() => ({ toast }), [])
  return <ToastContext.Provider value={context}>{children}<div className="toast-stack">{items.map((item) => <div className={`toast toast-${item.kind}`} key={item.id}>{item.kind === 'success' ? <CheckCircle2 size={18} /> : item.kind === 'error' ? <AlertCircle size={18} /> : <Info size={18} />}<span>{item.message}</span><button aria-label="Dismiss notification" onClick={() => setItems((current) => current.filter((toastItem) => toastItem.id !== item.id))}><X size={15} /></button></div>)}</div></ToastContext.Provider>
}
export function useToast() { const value = useContext(ToastContext); if (!value) throw new Error('useToast must be used within ToastProvider'); return value.toast }

export function Form({ children, onSubmit, className = '' }: { children: ReactNode; onSubmit: (event: FormEvent<HTMLFormElement>) => void; className?: string }) { return <form className={className} onSubmit={onSubmit}>{children}</form> }
export function Spinner({ label = 'Loading' }: { label?: string }) { return <span className="spinner-label"><LoaderCircle className="spinner" size={17} />{label}</span> }
