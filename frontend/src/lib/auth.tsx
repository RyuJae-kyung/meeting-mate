import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, tokenStore } from '../api/client'
import type { User } from '../api/types'

interface AuthCtx {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (data: { email: string; password: string; name: string; job_title?: string }) => Promise<void>
  logout: () => void
  setUser: (u: User) => void
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!tokenStore.get()) { setLoading(false); return }
    api.get<User>('/auth/me').then((r) => setUser(r.data)).catch(() => tokenStore.clear()).finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const r = await api.post('/auth/login', { email, password })
    tokenStore.set(r.data.access_token)
    setUser(r.data.user)
  }, [])

  const register = useCallback(async (data: { email: string; password: string; name: string; job_title?: string }) => {
    const r = await api.post('/auth/register', data)
    tokenStore.set(r.data.access_token)
    setUser(r.data.user)
  }, [])

  const logout = useCallback(() => { tokenStore.clear(); setUser(null) }, [])

  return <Ctx.Provider value={{ user, loading, login, register, logout, setUser }}>{children}</Ctx.Provider>
}

export function useAuth() {
  const c = useContext(Ctx)
  if (!c) throw new Error('AuthProvider missing')
  return c
}
