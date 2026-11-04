import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { PublicBriefing } from '../api/types'
import { Alert, ItemList, PageLoader, SourceBadge } from '../components/ui'
import { fmtRange } from '../lib/format'
import { BasisLegend } from './meeting/BriefingTab'
import { TermCard } from './meeting/GlossaryTab'
import { PersonalView } from './meeting/PersonalTab'

export default function PublicBriefingPage() {
  const { token } = useParams()
  const [d, setD] = useState<PublicBriefing | null>(null)
  const [err, setErr] = useState('')
  const [done, setDone] = useState<Record<number, boolean>>({})
  const storeKey = `mm_check_${token}`
  useEffect(() => {
    api.get<PublicBriefing>(`/public/briefings/${token}`).then((r) => setD(r.data)).catch((e) => setErr(errorMessage(e)))
    try { setDone(JSON.parse(localStorage.getItem(storeKey) || '{}')) } catch { /* ignore */ }
  }, [token, storeKey])
  function toggle(i: number) {
    const next = { ...done, [i]: !done[i] }
    setDone(next)
    try { localStorage.setItem(storeKey, JSON.stringify(next)) } catch { /* ignore */ }
  }

  if (err) return <div className="mx-auto max-w-2xl px-4 py-10"><Alert>{err}</Alert></div>
  if (!d) return <PageLoader />
  const checklist = [...d.checklist, ...(d.personal?.content.preparation ?? [])]
  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <header>
        <p className="text-xs font-medium text-indigo-600">Meeting Mate · 개인 사전 브리핑</p>
        <h1 className="mt-1 text-2xl font-semibold">{d.meeting_title}</h1>
        <p className="mt-1 text-sm text-gray-500">{fmtRange(d.start_at, d.end_at)}{d.location ? ` · ${d.location}` : ''}</p>
        {d.online_url && <a href={d.online_url} target="_blank" rel="noreferrer" className="text-sm text-indigo-600 hover:underline">온라인 회의 참여 링크</a>}
        <p className="mt-3 text-sm">{d.participant_name}님 ({d.participant_role || '참석자'}){d.participant_responsibility ? ` · ${d.participant_responsibility}` : ''}</p>
      </header>
      {d.personal?.source === 'mock' && <Alert kind="warning">이 브리핑은 개발용 Mock AI로 생성되었습니다. 실제 AI 분석 결과가 아닙니다.</Alert>}
      <section className="card p-5">
        <h2 className="mb-2 text-sm font-semibold">회의 목적</h2>
        <p className="text-sm text-gray-800">{d.meeting_purpose || '미입력'}</p>
        <h2 className="mb-2 mt-4 text-sm font-semibold">주요 안건</h2>
        <ol className="list-inside list-decimal space-y-1 text-sm">{d.agenda_items.map((a, i) => <li key={i}>{a}</li>)}</ol>
      </section>
      <section className="card p-5">
        <div className="mb-4 flex items-center justify-between gap-2"><h2 className="text-sm font-semibold">나를 위한 브리핑</h2><SourceBadge source={d.personal?.source} /></div>
        {d.personal ? <><div className="mb-4"><BasisLegend /></div><PersonalView c={d.personal.content} /></> : <p className="text-sm text-gray-400">아직 개인 브리핑이 준비되지 않았습니다.</p>}
      </section>
      <section className="card p-5">
        <h2 className="mb-3 text-sm font-semibold">준비 체크리스트</h2>
        {checklist.length ? (
          <ul className="space-y-2">
            {checklist.map((c, i) => (
              <li key={i}><label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-0.5" checked={!!done[i]} onChange={() => toggle(i)} /><span className={done[i] ? 'text-gray-400 line-through' : ''}>{c.text}</span></label></li>
            ))}
          </ul>
        ) : <ItemList items={[]} />}
        <p className="mt-3 text-xs text-gray-400">체크 상태는 이 브라우저에만 저장됩니다.</p>
      </section>
      {d.glossary.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold">알아두면 좋은 전문 용어</h2>
          <div className="grid gap-3 md:grid-cols-2">{d.glossary.map((t) => <TermCard key={t.id} t={t} />)}</div>
        </section>
      )}
    </div>
  )
}
