import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { SystemStatus, User } from '../api/types'
import { Alert, SectionTitle, Spinner } from '../components/ui'
import { useAuth } from '../lib/auth'

function Row({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 text-sm">
      <span className="text-gray-500">{label}</span>
      <span className={`text-right font-medium ${ok === false ? 'text-amber-700' : ok ? 'text-emerald-700' : ''}`}>{value}</span>
    </div>
  )
}

export default function SettingsPage() {
  const { user, setUser, logout } = useAuth()
  const nav = useNavigate()
  const [p, setP] = useState({ name: user?.name ?? '', job_title: user?.job_title ?? '', email_notifications: user?.email_notifications ?? true })
  const [pw, setPw] = useState({ current_password: '', new_password: '' })
  const [sys, setSys] = useState<SystemStatus | null>(null)
  const [msg, setMsg] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState('')
  useEffect(() => { api.get<SystemStatus>('/system/status').then((r) => setSys(r.data)).catch(() => {}) }, [])

  async function saveProfile(e: FormEvent) {
    e.preventDefault(); setBusy('p')
    try { const r = await api.put<User>('/auth/me', { ...p, job_title: p.job_title || null }); setUser(r.data); setMsg({ kind: 'success', text: '프로필이 저장되었습니다.' }) } catch (e) { setMsg({ kind: 'error', text: errorMessage(e) }) } finally { setBusy('') }
  }
  async function savePw(e: FormEvent) {
    e.preventDefault(); setBusy('pw')
    try { await api.put('/auth/password', pw); setPw({ current_password: '', new_password: '' }); setMsg({ kind: 'success', text: '비밀번호가 변경되었습니다.' }) } catch (e) { setMsg({ kind: 'error', text: errorMessage(e) }) } finally { setBusy('') }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-xl font-semibold">설정</h1>
      {msg && <Alert kind={msg.kind} onClose={() => setMsg(null)}>{msg.text}</Alert>}
      <section className="card p-5">
        <SectionTitle>사용자 정보</SectionTitle>
        <form onSubmit={saveProfile} className="space-y-3">
          <div><label className="label">이메일</label><input className="input bg-gray-50" value={user?.email ?? ''} disabled /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div><label className="label">이름</label><input className="input" required value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} /></div>
            <div><label className="label">직무</label><input className="input" value={p.job_title} onChange={(e) => setP({ ...p, job_title: e.target.value })} /></div>
          </div>
          <p className="text-xs text-gray-500">권한: {user?.role === 'admin' ? '관리자 (모든 회의 열람·수정)' : '일반 사용자'}</p>
          <SectionTitle>알림 설정</SectionTitle>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={p.email_notifications} onChange={(e) => setP({ ...p, email_notifications: e.target.checked })} />이메일 알림 받기</label>
          <p className="text-xs text-gray-500">켜 두면 내가 담당자인 후속 업무의 마감 {sys ? `${sys.task_reminder_days_before}일 전부터` : '임박 시'} 알림 이메일을 한 번 받습니다. 끄면 자동 알림을 받지 않습니다.</p>
          <button className="btn-primary" disabled={busy === 'p'}>{busy === 'p' && <Spinner />}저장</button>
        </form>
      </section>
      <section className="card p-5">
        <SectionTitle>비밀번호 변경</SectionTitle>
        <form onSubmit={savePw} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <div><label className="label">현재 비밀번호</label><input className="input" type="password" required value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></div>
          <div><label className="label">새 비밀번호 (8자 이상)</label><input className="input" type="password" required minLength={8} value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></div>
          <button className="btn-secondary" disabled={busy === 'pw'}>변경</button>
        </form>
      </section>
      <section className="card p-5">
        <SectionTitle>이메일 · API 연동 상태</SectionTitle>
        {sys ? (
          <div className="divide-y">
            <Row label="AI 분석" value={sys.ai_provider === 'openai' ? `OpenAI (${sys.ai_model})` : 'Mock AI (OPENAI_API_KEY 미설정)'} ok={sys.ai_provider === 'openai'} />
            <Row label="이메일 발송" value={sys.email_provider === 'resend' ? 'Resend 연결됨' : 'Mock (RESEND_API_KEY 미설정, 실제 발송 안 됨)'} ok={sys.email_provider === 'resend'} />
            <Row label="발신 주소" value={sys.email_from} />
            <Row label="예약 발송 스케줄러" value={sys.scheduler_enabled ? `동작 중 (${sys.scheduler_interval_seconds}초 간격)` : '꺼짐'} ok={sys.scheduler_enabled} />
            <Row label="후속 업무 마감 알림" value={sys.scheduler_enabled ? `마감 ${sys.task_reminder_days_before}일 전부터 1회 자동 발송` : '스케줄러 꺼짐'} ok={sys.scheduler_enabled} />
            <Row label="Google Calendar" value="API 연동 예정 · 현재는 .ics 파일 내보내기 지원" />
            <Row label="업로드 제한" value={`${sys.allowed_file_types.map((t) => t.toUpperCase()).join(', ')} · ${sys.max_upload_mb}MB`} />
          </div>
        ) : <p className="text-sm text-gray-400">불러오는 중...</p>}
        <p className="mt-3 text-xs text-gray-500">API 키는 보안을 위해 화면에서 입력하지 않고 백엔드 서버의 환경변수로만 설정합니다. (README 참고)</p>
      </section>
      <button className="btn-secondary" onClick={() => { logout(); nav('/login') }}>로그아웃</button>
    </div>
  )
}
