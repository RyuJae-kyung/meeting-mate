import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api/client'
import type { Briefing, GeneralBriefingContent, MeetingDetail } from '../../api/types'
import ItemsEditor, { cleanItems } from '../../components/ItemsEditor'
import { Alert, BasisBadge, EmptyState, ItemList, PageLoader, SourceBadge, Spinner } from '../../components/ui'
import { fmtDateTime } from '../../lib/format'

export const GENERAL_SECTIONS: [keyof GeneralBriefingContent, string][] = [
  ['purpose_summary', '1. 회의 목적 요약'], ['agenda_items', '2. 주요 안건 정리'], ['expected_discussions', '3. 핵심 논의 예상 사항'],
  ['pre_questions', '4. 사전에 확인해야 할 질문'], ['checklist', '5. 회의 전 준비 체크리스트'], ['issues', '6. 예상되는 쟁점 및 고려 사항'],
  ['material_summaries', '7. 관련 자료 핵심 요약'],
]

export function BasisLegend() {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
      <span className="flex items-center gap-1"><BasisBadge basis="fact" />자료·회의 정보에 명시</span>
      <span className="flex items-center gap-1"><BasisBadge basis="inference" />AI 예상 (결정 사항 아님)</span>
      <span className="flex items-center gap-1"><BasisBadge basis="uncertain" />불확실·확인 필요</span>
    </div>
  )
}

export default function BriefingTab({ m, onGenerate, generating }: { m: MeetingDetail; onGenerate: () => void; generating: boolean }) {
  const [b, setB] = useState<Briefing<GeneralBriefingContent> | null | undefined>(undefined)
  const [draft, setDraft] = useState<GeneralBriefingContent | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => { api.get(`/meetings/${m.id}/briefing`).then((r) => setB(r.data)).catch((e) => setErr(errorMessage(e))) }, [m.id])

  async function save() {
    if (!b || !draft) return
    setBusy(true); setErr('')
    const content = Object.fromEntries(GENERAL_SECTIONS.map(([k]) => [k, cleanItems(draft[k])]))
    try { const r = await api.put(`/briefings/${b.id}`, { content }); setB(r.data); setDraft(null); setSaved(true) } catch (e) { setErr(errorMessage(e)) } finally { setBusy(false) }
  }

  if (b === undefined) return err ? <Alert>{err}</Alert> : <PageLoader />
  if (b === null)
    return <EmptyState title="아직 생성된 브리핑이 없습니다" desc="회의 정보와 업로드 자료를 분석해 사전 브리핑, 전문 용어, 참석자별 브리핑을 한 번에 만듭니다."
      action={m.can_edit && <button className="btn-primary" onClick={onGenerate} disabled={generating}>{generating && <Spinner />}AI 브리핑 생성</button>} />

  const c = draft ?? b.content
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <SourceBadge source={b.source} />
          <span>생성 {fmtDateTime(b.created_at)}{b.is_edited ? ` · 수정됨 ${fmtDateTime(b.updated_at)}` : ''}</span>
        </div>
        {m.can_edit && (draft ? (
          <div className="flex gap-2"><button className="btn-secondary" onClick={() => setDraft(null)}>취소</button><button className="btn-primary" onClick={save} disabled={busy}>{busy && <Spinner />}저장</button></div>
        ) : <button className="btn-secondary" onClick={() => { setDraft(structuredClone(b.content)); setSaved(false) }}>브리핑 수정</button>)}
      </div>
      {b.source === 'mock' && <Alert kind="warning">OPENAI_API_KEY 가 설정되지 않아 <b>Mock AI</b>(규칙 기반)로 생성된 결과입니다. 실제 AI 분석 결과가 아닙니다.</Alert>}
      {err && <Alert onClose={() => setErr('')}>{err}</Alert>}
      {saved && <Alert kind="success" onClose={() => setSaved(false)}>브리핑이 저장되었습니다. 이메일 발송 시 수정된 내용이 사용됩니다.</Alert>}
      <BasisLegend />
      <div className="grid gap-4 md:grid-cols-2">
        {GENERAL_SECTIONS.map(([k, title]) => (
          <section key={k} className={`card p-5 ${draft ? 'md:col-span-2' : ''}`}>
            <h3 className="mb-3 text-sm font-semibold">{title}</h3>
            {draft ? <ItemsEditor items={draft[k]} onChange={(v) => setDraft({ ...draft, [k]: v })} /> : <ItemList items={c[k]} />}
          </section>
        ))}
      </div>
    </div>
  )
}
