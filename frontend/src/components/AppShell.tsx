import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Activity, BadgeIndianRupee, CircleHelp, FileUp, LayoutDashboard, LogOut, Menu, PackageCheck, ReceiptText, Scale, ShieldCheck, X } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'

const links = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/imports', label: 'File uploads', icon: FileUp },
  { to: '/reconciliation', label: 'Reconciliation', icon: Activity },
  { to: '/claims', label: 'Claims', icon: ReceiptText },
  { to: '/rate-cards', label: 'Rate cards', icon: Scale },
  { to: '/returns', label: 'Returns tracker', icon: PackageCheck },
  { to: '/analytics', label: 'Money at risk', icon: BadgeIndianRupee },
]
export function AppShell() {
  const { user, logout, hasRole } = useAuth(); const [open, setOpen] = useState(false)
  const allLinks = hasRole('FINANCE_COFOUNDER') ? [...links, { to: '/audit-users', label: 'Audit & users', icon: ShieldCheck }] : links
  return <div className="app-frame">
    {open && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setOpen(false)} />}
    <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
      <div className="brand"><div className="brand-logo"><Activity size={19} strokeWidth={2.5} /></div><span>recon<span className="brand-flow">flow</span></span><button className="sidebar-close" onClick={() => setOpen(false)} aria-label="Close menu"><X size={17} /></button></div>
      <div className="workspace-switch"><div className="workspace-avatar">R</div><div><b>ReconFlow Finance</b><small>Workspace</small></div></div>
      <div className="nav-label">WORKSPACE</div>
      <nav className="side-nav">{allLinks.map(({ to, label, icon: Icon }) => <NavLink end={to === '/'} to={to} key={to} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} onClick={() => setOpen(false)}><Icon size={17} /><span>{label}</span>{to === '/claims' && <span className="nav-dot" />}</NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-help"><div className="help-icon"><CircleHelp size={17} /></div><div><b>Need a hand?</b><small>Review your finance data</small></div></div><div className="user-menu"><div className="user-avatar">{user?.full_name?.slice(0, 1).toUpperCase() || 'U'}</div><div className="user-meta"><b>{user?.full_name || user?.email}</b><small>{user?.roles[0]?.replaceAll('_', ' ') || 'Finance user'}</small></div><button aria-label="Sign out" onClick={logout} title="Sign out"><LogOut size={16} /></button></div></div>
    </aside>
    <main className="main-area"><header className="topbar"><button className="mobile-menu" aria-label="Open navigation" onClick={() => setOpen(true)}><Menu size={20} /></button><div className="breadcrumb">Finance operations <span>/</span> <b>ReconFlow</b></div><div className="topbar-right"><span className="secure-label"><span /> Secure workspace</span><div className="topbar-divider" /><div className="topbar-user"><div className="user-avatar small">{user?.full_name?.slice(0, 1).toUpperCase()}</div><span>{user?.full_name?.split(' ')[0]}</span></div></div></header><div className="content-wrap"><Outlet /></div><footer className="footer"><span>ReconFlow Finance Workspace</span><span>Financial data is sourced from imported records</span></footer></main>
  </div>
}
