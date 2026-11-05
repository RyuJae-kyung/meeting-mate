import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { GenerateResult, MeetingDetail } from '../api/types'
import { Alert, PageLoader, Spinner, StatusBadge } from '../components/ui'
import { fmtRange } from '../lib/format'
import BriefingTab from './meeting/BriefingTab'
import EmailTab from './meeting/EmailTab'
import GlossaryTab from './meeting/GlossaryTab'
import MaterialsTab from './meeting/MaterialsTab'
import OverviewTab from './meeting/OverviewTab'
import PersonalTab from './meeting/PersonalTab'
import QATab from './meeting/QATab'
import ResultTab from './meeting/ResultTab'

const TABS = [
  ['overview', '회의 개요'], ['briefing', 'AI 사전 브리핑'], ['glossary', '전문 용어'],
  ['personal', '참석자별 브리핑'], ['materials', '업로드 자료'], ['qa', 'AI 질문하기'], ['email', '이메일 발송'],
  ['result', '회의 결과·후속 업무'],
] as const
type Tab = (typeof TABS)[number][0]

export default function MeetingDetailPage() {
  const { id } = useParams()
  const meetingId = Number(id)
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const nav = useNavigate()
  const [m, setM] = useState<MeetingDetail | null>(null)
  const [err, setErr] = useState('')
  const [notice, setNotice] = useState<string[]>((location.state as { warnings?: string[] } | null)?.warnings ?? [])
  const [generating, setGenerating] = useState(false)
  const [version, setVersion] = useState(0) // 브리핑 재생성 시 하위 탭 갱신용
  const tab = (params.get('tab') as Tab) || 'overview'

  const reload = useCallback(() => api.get<MeetingDetail>(`/meetings/${meetingId}`).then((r) => setM(r.data)).catch((e) => setErr(errorMessage(e))), [meetingId])
  useEffect(() => { reload() }, [reload])

  async function generate() {
    if (m?.has_briefing && !confirm('브리핑을 다시 생성하면 직접 수정한 브리핑·용어 내용이 새 결과로 교체됩니다. 계속할까요?')) return
    setGenerating(true); setErr('')
    try {
      const r = await api.post<GenerateResult>(`/meetings/${meetingId}/briefings/generate`)
      setNotice([`브리핑 생성 완료 · 전문 용어 ${r.data.glossary_count}개 · 참석자별 브리핑 ${r.data.participant_briefing_count}건${r.data.source === 'mock' ? ' (Mock AI)' : ''}`, ...r.data.warnings])
      await reload()
      setVersion((v) => v + 1)
      setParams({ tab: 'briefing' })
    } catch (e) { setErr(errorMessage(e)) } finally { setGenerating(false) }
  }

  async function downloadIcs() {
    try {
      const r = await api.get(`/meetings/${meetingId}/ics`, { responseType: 'blob' })
      const url = URL.createObjectURL(r.data as Blob)
      const a = document.createElement('a')
      a.href = url; a.download = `meeting-${meetingId}.ics`; a.click()
      URL.revokeObjectURL(url)
    } catch (e) { setErr(errorMessage(e)) }
  }

  if (err && !m) return <div className="space-y-3"><Alert>{err}</Alert><Link to="/meetings" className="btn-secondary">회의 목록으로</Link></div>
  if (!m) return <PageLoader />
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2"><h1 className="truncate text-xl font-semibold">{m.title}</h1><StatusBadge status={m.status} /></div>
          <p className="mt-1 text-sm text-gray-500">{fmtRange(m.start_at, m.end_at)}{m.location ? ` · ${m.location}` : ''} · 주최 {m.owner_name}</p>
        </div>
        <div className="flex flex-wrap gap-2">
        <button className="btn-secondary" onClick={downloadIcs} title="Google Calendar·Outlook 등에서 가져올 수 있는 .ics 파일">캘린더에 추가</button>
        {m.can_edit && (
          <button className="btn-primary" onClick={generate} disabled={generating}>
            {generating && <Spinner />}{generating ? 'AI 분석 중... (최대 1~2분)' : m.has_briefing ? '브리핑 다시 생성' : 'AI 브리핑 생성'}
          </button>
        )}
        </div>
      </div>
      {err && <Alert onClose={() => setErr('')}>{err}</Alert>}
      {notice.length > 0 && <Alert kind="info" onClose={() => setNotice([])}>{notice.map((n, i) => <div key={i}>{n}</div>)}</Alert>}

      <div className="-mx-4 overflow-x-auto border-b px-4 md:mx-0 md:px-0">
        <nav className="flex gap-1">
          {TABS.filter(([k]) => m.can_edit || k !== 'email').map(([k, label]) => (
            <button key={k} onClick={() => setParams({ tab: k })}
              className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm ${tab === k ? 'border-indigo-600 font-medium text-gray-900' : 'border-transparent text-gray-500 hover:text-gray-800'}`}>
              {label}
            </button>
          ))}
        </nav>
      </div>

      <div key={version}>
        {tab === 'overview' && <OverviewTab m={m} reload={reload} onDeleted={() => nav('/meetings')} />}
        {tab === 'briefing' && <BriefingTab m={m} onGenerate={generate} generating={generating} />}
        {tab === 'glossary' && <GlossaryTab m={m} />}
        {tab === 'personal' && <PersonalTab m={m} />}
        {tab === 'materials' && <MaterialsTab m={m} reload={reload} />}
        {tab === 'qa' && <QATab m={m} />}
        {tab === 'email' && m.can_edit && <EmailTab m={m} />}
        {tab === 'result' && <ResultTab m={m} reload={reload} />}
      </div>
    </div>
  )
}
