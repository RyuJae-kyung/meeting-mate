import axios, { AxiosError } from 'axios'

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || 'http://localhost:8000'
const TOKEN_KEY = 'mm_token'

export const tokenStore = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } },
  set: (t: string) => { try { localStorage.setItem(TOKEN_KEY, t) } catch { /* ignore */ } },
  clear: () => { try { localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ } },
}

export const api = axios.create({ baseURL: `${API_URL}/api`, timeout: 180_000 })

api.interceptors.request.use((config) => {
  const t = tokenStore.get()
  if (t) config.headers.Authorization = `Bearer ${t}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err: AxiosError) => {
    if (err.response?.status === 401 && !err.config?.url?.startsWith('/auth/login')) {
      tokenStore.clear()
      if (!location.pathname.startsWith('/login') && !location.pathname.startsWith('/b/')) {
        location.href = `/login?next=${encodeURIComponent(location.pathname)}`
      }
    }
    return Promise.reject(err)
  },
)

export function errorMessage(err: unknown, fallback = '요청 처리 중 오류가 발생했습니다.'): string {
  if (axios.isAxiosError(err)) {
    if (!err.response) return '서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인해 주세요.'
    const d = (err.response.data as { detail?: unknown })?.detail
    if (typeof d === 'string') return d
    return `${fallback} (HTTP ${err.response.status})`
  }
  return fallback
}
