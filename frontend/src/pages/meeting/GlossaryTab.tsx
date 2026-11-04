import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api/client'
import type { GlossaryTerm, MeetingDetail } from '../../api/types'
import { Alert, EmptyState, Modal, PageLoader, SourceBadge, Spinner } from '../../components/ui'

export function TermCard({ t, actions }: { t: GlossaryTerm; actions?: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-base font-semibold">{t.term}</h3>
          {t.is_uncertain && <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-700">확인 필요</span>}
          {t.is_edited && <span className="text-[11px] text-gray-400">수정됨</span>}
        </div>
        {actions}
      </div>
      <p className="text-sm text-gray-800">{t.easy_explanation}</p>
      {t.work_meaning && <p className="mt-2 text-sm text-gray-600"><span className="font-medium text-gray-500">실무 의미 </span>{t.work_meaning}</p>}
      {t.why_important && <p className="mt-1 text-sm text-gray-600"><span className="font-medium text-gray-500">알아둘 이유 </span>{t.why_important}</p>}
      {t.context && (
        <blockquote className="mt-2 border-l-2 border-gray-200 pl-3 text-xs text-gray-500">
          “{t.context}”{t.source_ref && <span className="ml-1 text-gray-400">— {t.source_ref}</span>}
        </blockquote>
      )}
      {t.related_concepts.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">{t.related_concepts.map((r) => <span key={r} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">{r}</span>)}</div>
      )}
    </div>
  )
}

export default function GlossaryTab({ m }: { m: MeetingDetail }) {
  const [terms, setTerms] = useState<GlossaryTerm[] | null>(null)
  const [edit, setEdit] = useState<GlossaryTerm | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { api.get(`/meetings/${m.id}/glossary`).then((r) => setTerms(r.data)).catch((e) => setErr(errorMessage(e))) }, [m.id])

  async function save() {
    if (!edit) return
    setBusy(true)
    try {
      const r = await api.put<GlossaryTerm>(`/glossary/${edit.id}`, {
        term: edit.term, easy_explanation: edit.easy_explanation, work_meaning: edit.work_meaning, why_important: edit.why_important,
        related_concepts: edit.related_concepts,
      })
      setTerms((ts) => ts!.map((t) => (t.id === r.data.id ? r.data : t))); setEdit(null)
    } catch (e) { setErr(errorMessage(e)) } finally { setBusy(false) }
  }
  async function remove(t: GlossaryTerm) {
    if (!confirm(`'${t.term}' 용어를 삭제할까요?`)) return
    try { await api.delete(`/glossary/${t.id}`); setTerms((ts) => ts!.filter((x) => x.id !== t.id)) } catch (e) { setErr(errorMessage(e)) }
  }

  if (!terms) return err ? <Alert>{err}</Alert> : <PageLoader />
  if (!terms.length) return <EmptyState title="추출된 전문 용어가 없습니다" desc="자료를 업로드한 뒤 AI 브리핑을 생성하면 용어가 자동으로 추출됩니다." />
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-xs text-gray-500"><SourceBadge source={terms[0].source} /><span>회의 자료에서 추출한 용어 {terms.length}개 · 회의 맥락 기준 설명</span></div>
      {err && <Alert onClose={() => setErr('')}>{err}</Alert>}
      <div className="grid gap-3 md:grid-cols-2">
        {terms.map((t) => (
          <TermCard key={t.id} t={t} actions={m.can_edit && (
            <div className="flex shrink-0 gap-1"><button className="btn-ghost text-xs" onClick={() => setEdit({ ...t })}>수정</button><button className="btn-ghost text-xs text-red-600" onClick={() => remove(t)}>삭제</button></div>
          )} />
        ))}
      </div>
      <Modal open={!!edit} title="용어 설명 수정" onClose={() => setEdit(null)}
        footer={<><button className="btn-secondary" onClick={() => setEdit(null)}>취소</button><button className="btn-primary" onClick={save} disabled={busy}>{busy && <Spinner />}저장</button></>}>
        {edit && (
          <div className="space-y-3">
            <div><label className="label">용어</label><input className="input" value={edit.term} onChange={(e) => setEdit({ ...edit, term: e.target.value })} /></div>
            <div><label className="label">쉬운 설명</label><textarea className="input" rows={3} value={edit.easy_explanation} onChange={(e) => setEdit({ ...edit, easy_explanation: e.target.value })} /></div>
            <div><label className="label">실무에서의 의미</label><textarea className="input" rows={2} value={edit.work_meaning} onChange={(e) => setEdit({ ...edit, work_meaning: e.target.value })} /></div>
            <div><label className="label">알아두면 좋은 이유</label><textarea className="input" rows={2} value={edit.why_important} onChange={(e) => setEdit({ ...edit, why_important: e.target.value })} /></div>
            <div><label className="label">관련 개념 (쉼표로 구분)</label><input className="input" value={edit.related_concepts.join(', ')} onChange={(e) => setEdit({ ...edit, related_concepts: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} /></div>
          </div>
        )}
      </Modal>
    </div>
  )
}
