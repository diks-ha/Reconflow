import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, TOKEN_KEY } from '../api/client'
import type { User } from '../api/types'

type AuthValue = { user: User | null; loading: boolean; login: (email: string, password: string) => Promise<void>; logout: () => void; refresh: () => Promise<void>; hasRole: (...roles: string[]) => boolean }
const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const logout = useCallback(() => { sessionStorage.removeItem(TOKEN_KEY); setUser(null) }, [])
  const refresh = useCallback(async () => {
    if (!sessionStorage.getItem(TOKEN_KEY)) { setUser(null); setLoading(false); return }
    try { const { data } = await api.get<User>('/auth/me'); setUser(data) }
    catch { logout() }
    finally { setLoading(false) }
  }, [logout])
  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post<{ access_token: string }>('/auth/login', { email, password })
    sessionStorage.setItem(TOKEN_KEY, data.access_token)
    await refresh()
  }, [refresh])
  useEffect(() => { localStorage.removeItem(TOKEN_KEY); void refresh(); const handler = () => logout(); window.addEventListener('reconflow:unauthorized', handler); return () => window.removeEventListener('reconflow:unauthorized', handler) }, [refresh, logout])
  const value: AuthValue = { user, loading, login, logout, refresh, hasRole: (...roles) => !!user?.roles.some((role) => roles.includes(role)) }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() { const value = useContext(AuthContext); if (!value) throw new Error('useAuth must be used within AuthProvider'); return value }
