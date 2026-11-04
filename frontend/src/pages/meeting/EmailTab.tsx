import { useCallback, useEffect, useState } from 'react'
import { api, errorMessage } from '../../api/client'
import type { EmailJob, EmailLog, EmailPreview, MeetingDetail, SystemStatus } from '../../api/types'
import { Alert, Modal, SectionTitle, Spinner } from '../../components/ui'
import { fmtDateTime, localInputToIso } from '../../lib/format'

export const JOB_MODE: Record<EmailJob['mode'], string> = { now: '즉시 발송', scheduled: '예약 발송', before_meeting: '회의 전 자동 발송' }
const JOB_STATUS: Record<string, [string, string]> = {
  pending: ['대기', 'bg-indigo-50 text-indigo-700'], processing: ['처리 중', 'bg-indigo-50 text-indigo-700'],
  done: ['완료', 'bg-emerald-50 text-emerald-700'], partial: ['일부 실패', 'bg-amber-50 text-amber-700'],
  failed: ['실패', 'bg-red-50 text-red-600'], cancelled: ['취소됨', 'bg-gray-100 text-gray-500'],
}
const BEFORE_OPTS = [[30, '30분 전'], [60, '1시간 전'], [180, '3시간 전'], [1440, '하루 전'], [2880, '이틀 전']] as const

export function EmailStatusBadge({ status, provider }: { status: string; provider: string }) {
  const cls = status === 'sent' ? 'bg-emerald-50 text-emerald-700' : status === 'failed' ? 'bg-red-50 text-red-600' : 'bg-gray-100 text-gray-600'
  const label = status === 'sent' ? (provider === 'mock' ? '발송됨(Mock)' : '발송됨') : status === 'failed' ? '실패' : '재시도 중'
  return <span title={provider === 'mock' ? 'Mock 모드: 실제 메일은 발송되지 않았습니다' : undefined} className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>{label}</span>
}

export default function EmailTab({ m }: { m: MeetingDetail }) {
  const [selected, setSelected] = useState<number[]>(m.participants.map((p) => p.id))
  const [mode, setMode] = useState<EmailJob['mode']>('now')
  const [at, setAt] = useState('')
  const [before, setBefore] = useState(60)
  const [preview, setPreview] = useState<EmailPreview | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [checked, setChecked] = useState(false)
  const [logs, setLogs] = useState<EmailLog[]>([])
  const [jobs, setJobs] = useState<EmailJob[]>([])
  const [body, setBody] = useState<string | null>(null)
  const [sys, setSys] = useState<SystemStatus | null>(null)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')

  const load = useCallback(async () => {
    const [l, j] = await Promise.all([api.get<EmailLog[]>(`/meetings/${m.id}/emails/logs`), api.get<EmailJob[]>(`/meetings/${m.id}/emails/jobs`)])
    setLogs(l.data); setJobs(j.data)
  }, [m.id])
  useEffect(() => { load().catch((e) => setErr(errorMessage(e))); api.get<SystemStatus>('/system/status').then((r) => setSys(r.data)).catch(() => {}) }, [load])
  // 대기 중 예약이 있으면 30초마다 상태 갱신
  useEffect(() => {
    if (!jobs.some((j) => j.status === 'pending' || j.status === 'processing')) return
    const t = setInterval(() => load().catch(() => {}), 30_000)
    return () => clearInterval(t)
  }, [jobs, load])

  const name = (pid: number | null) => m.participants.find((p) => p.id === pid)?.name ?? '(삭제된 참석자)'
  const scheduledAt = mode === 'scheduled' ? (at ? new Date(at) : null) : mode === 'before_meeting' ? new Date(new Date(m.start_at).getTime() - before * 60000) : new Date()

  async function openPreview(pid: number) {
    setBusy(`pv-${pid}`); setErr('')
    try { setPreview((await api.post<EmailPreview>(`/meetings/${m.id}/emails/preview`, { participant_id: pid })).data) } catch (e) { setErr(errorMessage(e)) } finally { setBusy('') }
  }
  function startSend() {
    setErr(''); setOk('')
    if (!selected.length) { setErr('수신자를 한 명 이상 선택해 주세요.'); return }
    if (mode === 'scheduled' && !at) { setErr('예약 발송 시각을 입력해 주세요.'); return }
    if (mode !== 'now' && scheduledAt && scheduledAt.getTime() <= Date.now() + 60_000) { setErr('발송 예정 시각이 이미 지났거나 너무 가깝습니다.'); return }
    setChecked(false); setConfirmOpen(true)
  }
  async function send() {
    setBusy('send'); setErr('')
    try {
      const r = await api.post(`/meetings/${m.id}/emails/send`, {
        participant_ids: selected, mode, confirm: true,
        scheduled_at: mode === 'scheduled' ? localInputToIso(at) : undefined,
        minutes_before: mode === 'before_meeting' ? before : undefined,
      })
      const logs_: EmailLog[] = r.data.logs
      if (mode === 'now') {
        const failed = logs_.filter((l) => l.status === 'failed').length
        setOk(`${logs_.length - failed}건 발송 완료${failed ? `, ${failed}건 실패 (아래 내역에서 재시도할 수 있습니다)` : ''}${logs_[0]?.provider === 'mock' ? ' · Mock 모드: 실제 메일은 발송되지 않았습니다' : ''}`)
      } else setOk(`${fmtDateTime(r.data.job.scheduled_at)}에 ${selected.length}명에게 발송되도록 예약했습니다.`)
      setConfirmOpen(false)
      await load()
    } catch (e) { setErr(errorMessage(e)); setConfirmOpen(false) } finally { setBusy('') }
  }
  async function retry(id: number) {
    setBusy(`rt-${id}`); setErr('')
    try { const r = await api.post<EmailLog>(`/emails/logs/${id}/retry`); setOk(r.data.status === 'sent' ? '재발송에 성공했습니다.' : ''); if (r.data.status === 'failed') setErr(`재시도 실패: ${r.data.error}`); await load() } catch (e) { setErr(errorMessage(e)) } finally { setBusy('') }
  }
  async function cancel(id: number) {
    if (!confirm('이 예약 발송을 취소할까요?')) return
    try { await api.post(`/emails/jobs/${id}/cancel`); await load() } catch (e) { setErr(errorMessage(e)) }
  }
  async function viewBody(id: number) {
    try { setBody((await api.get(`/emails/logs/${id}`)).data.body_html) } catch (e) { setErr(errorMessage(e)) }
  }

  const noBriefing = !m.has_briefing
  return (
    <div className="space-y-6">
      {sys?.email_provider === 'mock' && <Alert kind="warning">RESEND_API_KEY 가 설정되지 않아 <b>Mock 이메일 모드</b>입니다. 발송 기록과 본문은 저장되지만 실제 메일은 전송되지 않습니다.</Alert>}
      {noBriefing && <Alert kind="info">먼저 'AI 브리핑 생성'을 실행해야 참석자별 브리핑 이메일을 보낼 수 있습니다.</Alert>}
      {err && <Alert onClose={() => setErr('')}>{err}</Alert>}
      {ok && <Alert kind="success" onClose={() => setOk('')}>{ok}</Alert>}

      <section className="card p-5">
        <SectionTitle>브리핑 이메일 발송</SectionTitle>
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="label mb-0">수신자</p>
              <button className="text-xs text-indigo-600" onClick={() => setSelected(selected.length === m.participants.length ? [] : m.participants.map((p) => p.id))}>{selected.length === m.participants.length ? '전체 해제' : '전체 선택'}</button>
            </div>
            <div className="divide-y rounded-md border">
              {m.participants.map((p) => (
                <div key={p.id} className="flex items-center justify-between gap-2 px-3 py-2">
                  <label className="flex min-w-0 items-center gap-2 text-sm">
                    <input type="checkbox" checked={selected.includes(p.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, p.id] : selected.filter((x) => x !== p.id))} />
                    <span className="truncate">{p.name} <span className="text-xs text-gray-500">{p.email}</span></span>
                  </label>
                  <button className="btn-ghost shrink-0 text-xs" onClick={() => openPreview(p.id)} disabled={noBriefing || !!busy}>{busy === `pv-${p.id}` && <Spinner className="h-3 w-3" />}미리보기</button>
                </div>
              ))}
              {!m.participants.length && <p className="px-3 py-3 text-sm text-gray-400">참석자가 없습니다.</p>}
            </div>
          </div>
          <div className="space-y-3">
            <p className="label mb-0">발송 방식</p>
            {(['now', 'scheduled', 'before_meeting'] as const).map((v) => (
              <label key={v} className="flex items-center gap-2 text-sm"><input type="radio" checked={mode === v} onChange={() => setMode(v)} />{JOB_MODE[v]}</label>
            ))}
            {mode === 'scheduled' && <input className="input" type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} aria-label="예약 시각" />}
            {mode === 'before_meeting' && (
              <div className="space-y-1">
                <select className="input" value={before} onChange={(e) => setBefore(Number(e.target.value))} aria-label="회의 몇 분 전">
                  {BEFORE_OPTS.map(([v, l]) => <option key={v} value={v}>회의 {l}</option>)}
                </select>
                <p className="text-xs text-gray-500">발송 예정: {scheduledAt ? fmtDateTime(scheduledAt.toISOString()) : '-'}</p>
              </div>
            )}
            {mode !== 'now' && <p className="text-xs text-gray-500">예약 발송은 발송 시점의 최신 브리핑 내용으로 전송됩니다{sys ? ` (약 ${sys.scheduler_interval_seconds}초 간격으로 확인)` : ''}.</p>}
            <button className="btn-primary w-full" onClick={startSend} disabled={noBriefing || !selected.length}>발송 확인으로 이동</button>
          </div>
        </div>
      </section>

      {jobs.some((j) => j.mode !== 'now') && (
        <section className="card p-5">
          <SectionTitle>예약 발송</SectionTitle>
          <div className="divide-y">
            {jobs.filter((j) => j.mode !== 'now').map((j) => {
              const [label, cls] = JOB_STATUS[j.status] ?? [j.status, 'bg-gray-100']
              return (
                <div key={j.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                  <div>
                    <p>{fmtDateTime(j.scheduled_at)} <span className="text-xs text-gray-500">· {JOB_MODE[j.mode]}{j.minutes_before ? ` (${j.minutes_before}분 전)` : ''} · {j.participant_ids.length}명</span></p>
                    {j.error && <p className="text-xs text-red-600">{j.error}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>{label}</span>
                    {j.status === 'pending' && <button className="btn-ghost text-xs text-red-600" onClick={() => cancel(j.id)}>취소</button>}
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      <section className="card p-5">
        <SectionTitle right={<button className="btn-ghost text-xs" onClick={() => load().catch((e) => setErr(errorMessage(e)))}>새로고침</button>}>발송 내역</SectionTitle>
        {!logs.length ? <p className="text-sm text-gray-400">발송 내역이 없습니다.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-xs text-gray-500"><th className="py-2 pr-3 font-medium">수신자</th><th className="py-2 pr-3 font-medium">상태</th><th className="py-2 pr-3 font-medium">시각</th><th className="py-2 pr-3 font-medium">시도</th><th className="py-2 font-medium"></th></tr></thead>
              <tbody className="divide-y">
                {logs.map((l) => (
                  <tr key={l.id}>
                    <td className="py-2 pr-3"><p>{name(l.participant_id)}</p><p className="text-xs text-gray-500">{l.recipient}</p>{l.error && <p className="max-w-md text-xs text-red-600">{l.error}</p>}</td>
                    <td className="py-2 pr-3"><EmailStatusBadge status={l.status} provider={l.provider} /></td>
                    <td className="whitespace-nowrap py-2 pr-3 text-xs text-gray-500">{fmtDateTime(l.sent_at || l.created_at)}</td>
                    <td className="py-2 pr-3 text-xs text-gray-500">{l.attempts}</td>
                    <td className="whitespace-nowrap py-2 text-right">
                      {l.status === 'sent' && <button className="btn-ghost text-xs" onClick={() => viewBody(l.id)}>본문</button>}
                      {l.status === 'failed' && <button className="btn-secondary text-xs" onClick={() => retry(l.id)} disabled={!!busy}>{busy === `rt-${l.id}` && <Spinner className="h-3 w-3" />}재시도</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Modal open={!!preview} title="이메일 미리보기" onClose={() => setPreview(null)} wide>
        {preview && (
          <div className="space-y-2">
            <p className="text-sm"><span className="text-gray-500">받는 사람</span> {preview.to}</p>
            <p className="text-sm"><span className="text-gray-500">제목</span> {preview.subject}</p>
            <iframe title="미리보기" sandbox="" srcDoc={preview.html} className="h-[60vh] w-full rounded border" />
          </div>
        )}
      </Modal>
      <Modal open={body !== null} title="발송된 본문" onClose={() => setBody(null)} wide>
        {body !== null && <iframe title="본문" sandbox="" srcDoc={body} className="h-[60vh] w-full rounded border" />}
      </Modal>
      <Modal open={confirmOpen} title="발송 확인" onClose={() => setConfirmOpen(false)}
        footer={<><button className="btn-secondary" onClick={() => setConfirmOpen(false)}>취소</button><button className="btn-primary" onClick={send} disabled={!checked || busy === 'send'}>{busy === 'send' && <Spinner />}{mode === 'now' ? `${selected.length}명에게 발송` : '예약 등록'}</button></>}>
        <div className="space-y-3 text-sm">
          <p><span className="text-gray-500">방식</span> {JOB_MODE[mode]}{mode !== 'now' && scheduledAt ? ` · ${fmtDateTime(scheduledAt.toISOString())}` : ''}</p>
          <div>
            <p className="text-gray-500">수신자 {selected.length}명</p>
            <ul className="mt-1 max-h-40 overflow-y-auto rounded border px-3 py-2">{m.participants.filter((p) => selected.includes(p.id)).map((p) => <li key={p.id}>{p.name} &lt;{p.email}&gt;</li>)}</ul>
          </div>
          {sys?.email_provider === 'mock' && <p className="text-amber-700">Mock 모드이므로 실제 메일은 발송되지 않습니다.</p>}
          <label className="flex items-start gap-2"><input type="checkbox" className="mt-0.5" checked={checked} onChange={(e) => setChecked(e.target.checked)} />미리보기로 내용을 확인했으며, 위 수신자에게 발송하는 것에 동의합니다.</label>
        </div>
      </Modal>
    </div>
  )
}
