import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { AppShell } from './components/AppShell'
import { Spinner } from './components/UI'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { UploadPage } from './pages/UploadPage'
import { MappingPage } from './pages/MappingPage'
import { ReconciliationPage } from './pages/ReconciliationPage'
import { OrderDetailPage } from './pages/OrderDetailPage'
import { ClaimsPage } from './pages/ClaimsPage'
import { RateCardsPage } from './pages/RateCardsPage'
import { ReturnsPage } from './pages/ReturnsPage'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { AuditUsersPage } from './pages/AuditUsersPage'

function Protected() { const { user, loading } = useAuth(); if (loading) return <div className="screen-loader"><Spinner label="Loading your workspace" /></div>; return user ? <Outlet /> : <Navigate to="/login" replace /> }
function CofounderOnly() { const { hasRole } = useAuth(); return hasRole('FINANCE_COFOUNDER') ? <Outlet /> : <Navigate to="/" replace /> }
export default function App() {
  const { user } = useAuth()
  return <Routes><Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} /><Route element={<Protected />}><Route element={<AppShell />}>
    <Route index element={<DashboardPage />} /><Route path="imports" element={<UploadPage />} /><Route path="imports/:importId/mapping" element={<MappingPage />} />
    <Route path="reconciliation" element={<ReconciliationPage />} /><Route path="orders/:resultId" element={<OrderDetailPage />} />
    <Route path="claims" element={<ClaimsPage />} /><Route path="rate-cards" element={<RateCardsPage />} /><Route path="returns" element={<ReturnsPage />} /><Route path="analytics" element={<AnalyticsPage />} />
    <Route element={<CofounderOnly />}><Route path="audit-users" element={<AuditUsersPage />} /></Route>
  </Route></Route><Route path="*" element={<Navigate to={user ? '/' : '/login'} replace />} /></Routes>
}
