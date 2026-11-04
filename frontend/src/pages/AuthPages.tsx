import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { Alert, Spinner } from '../components/ui'
import { useAuth } from '../lib/auth'

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-600 font-bold text-white">M</div>
          <h1 className="text-xl font-semibold">{title}</h1>
          <p className="mt-1 text-sm text-gray-500">회의 전 준비부터 회의 후 실행까지</p>
        </div>
        <div className="card p-6">{children}</div>
      </div>
    </div>
  )
}

export function LoginPage() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [params] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setErr(''); setBusy(true)
    try {
      await login(email, password)
      nav(params.get('next') || '/', { replace: true })
    } catch (e) { setErr(errorMessage(e, '로그인에 실패했습니다.')) } finally { setBusy(false) }
  }

  return (
    <Shell title="Meeting Mate 로그인">
      <form onSubmit={submit} className="space-y-4">
        {err && <Alert>{err}</Alert>}
        <div><label className="label" htmlFor="email">이메일</label><input id="email" className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></div>
        <div><label className="label" htmlFor="pw">비밀번호</label><input id="pw" className="input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></div>
        <button className="btn-primary w-full py-2" disabled={busy}>{busy && <Spinner />}로그인</button>
      </form>
      <p className="mt-4 text-center text-sm text-gray-500">계정이 없으신가요? <Link to="/register" className="font-medium text-indigo-600">회원가입</Link></p>
    </Shell>
  )
}

export function RegisterPage() {
  const { register } = useAuth()
  const nav = useNavigate()
  const [f, setF] = useState({ name: '', email: '', password: '', job_title: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (f.password.length < 8) { setErr('비밀번호는 8자 이상이어야 합니다.'); return }
    setErr(''); setBusy(true)
    try {
      await register({ ...f, job_title: f.job_title || undefined })
      nav('/', { replace: true })
    } catch (e) { setErr(errorMessage(e, '회원가입에 실패했습니다.')) } finally { setBusy(false) }
  }

  return (
    <Shell title="회원가입">
      <form onSubmit={submit} className="space-y-4">
        {err && <Alert>{err}</Alert>}
        <div><label className="label" htmlFor="name">이름</label><input id="name" className="input" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
        <div><label className="label" htmlFor="email">이메일</label><input id="email" className="input" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
        <div><label className="label" htmlFor="pw">비밀번호 (8자 이상)</label><input id="pw" className="input" type="password" required minLength={8} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} autoComplete="new-password" /></div>
        <div><label className="label" htmlFor="job">직무 (선택)</label><input id="job" className="input" placeholder="예: 백엔드 개발, 서비스 기획" value={f.job_title} onChange={(e) => setF({ ...f, job_title: e.target.value })} /></div>
        <button className="btn-primary w-full py-2" disabled={busy}>{busy && <Spinner />}가입하기</button>
      </form>
      <p className="mt-4 text-center text-sm text-gray-500">이미 계정이 있으신가요? <Link to="/login" className="font-medium text-indigo-600">로그인</Link></p>
    </Shell>
  )
}
