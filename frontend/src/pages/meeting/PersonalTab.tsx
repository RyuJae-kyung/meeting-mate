import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api/client'
import type { Briefing, BriefingItem, MeetingDetail, Participant, PersonalBriefingContent } from '../../api/types'
import ItemsEditor, { cleanItems } from '../../components/ItemsEditor'
import { Alert, EmptyState, ItemList, PageLoader, SourceBadge, Spinner } from '../../components/ui'
import { BasisLegend } from './BriefingTab'

interface Row { participant: Participant; briefing: Briefing<PersonalBriefingContent> | null }
const SECTIONS: [keyof Omit<PersonalBriefingContent, 'focus_summary' | 'related_terms'>, string][] = [
  ['key_agenda', '본인에게 중요한 안건'], ['materials_to_review', '사전에 확인해야 할 자료'],
  ['expected_questions', '예상 질문'], ['preparation', '본인이 준비해야 할 내용'],
]

export function PersonalView({ c }: { c: PersonalBriefingContent }) {
  return (
    <div className="space-y-5">
      {c.focus_summary && <p className="rounded-md bg-indigo-50 px-4 py-3 text-sm text-indigo-900">{c.focus_summary}</p>}
      {SECTIONS.map(([k, t]) => (
        <section key={k}><h4 className="mb-2 text-sm font-semibold">{t}</h4><ItemList items={c[k] as BriefingItem[]} /></section>
      ))}
      <section>
        <h4 className="mb-2 text-sm font-semibold">관련 전문 용어</h4>
        {c.related_terms.length ? <div className="flex flex-wrap gap-1">{c.related_terms.map((t) => <span key={t} className="rounded bg-gray-100 px-2 py-0.5 text-xs">{t}</span>)}</div> : <p className="text-sm text-gray-400">없음</p>}
      </section>
    </div>
  )
}

export default function PersonalTab({ m }: { m: MeetingDetail }) {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [sel, setSel] = useState<number | null>(null)
  const [draft, setDraft] = useState<PersonalBriefingContent | null>(null)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.get<Row[]>(`/meetings/${m.id}/participant-briefings`).then((r) => { setRows(r.data); setSel(r.data[0]?.participant.id ?? null) }).catch((e) => setErr(errorMessage(e)))
  }, [m.id])

  const row = rows?.find((r) => r.participant.id === sel)
  const replace = (b: Briefing<PersonalBriefingContent>) => setRows((rs) => rs!.map((r) => (r.participant.id === b.participant_id ? { ...r, briefing: b } : r)))

  async function regenerate() {
    if (!row) return
    if (row.briefing?.is_edited && !confirm('직접 수정한 내용이 새 결과로 교체됩니다. 계속할까요?')) return
    setBusy('regen'); setErr('')
    try { const r = await api.post(`/participants/${row.participant.id}/briefing/regenerate`); replace(r.data) } catch (e) { setErr(errorMessage(e)) } finally { setBusy('') }
  }
  async function save() {
    if (!row?.briefing || !draft) return
    setBusy('save'); setErr('')
    const content = { ...draft, ...Object.fromEntries(SECTIONS.map(([k]) => [k, cleanItems(draft[k] as BriefingItem[])])) }
    try { const r = await api.put(`/briefings/${row.briefing.id}`, { content }); replace(r.data); setDraft(null) } catch (e) { setErr(errorMessage(e)) } finally { setBusy('') }
  }
  async function copyLink(p: Participant) {
    const url = `${location.origin}/b/${p.access_token}`
    try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { prompt('개인 브리핑 링크', url) }
  }

  if (!rows) return err ? <Alert>{err}</Alert> : <PageLoader />
  if (!rows.length) return <EmptyState title={m.can_edit ? '참석자가 없습니다' : '이 회의에 대한 본인 브리핑이 없습니다'} desc={m.can_edit ? "'회의 개요' 탭에서 참석자를 추가해 주세요." : undefined} />
  return (
    <div className="grid gap-4 md:grid-cols-[220px_1fr]">
      <div className="card h-fit divide-y">
        {rows.map((r) => (
          <button key={r.participant.id} onClick={() => { setSel(r.participant.id); setDraft(null) }}
            className={`block w-full px-4 py-2.5 text-left ${sel === r.participant.id ? 'bg-indigo-50' : 'hover:bg-gray-50'}`}>
            <p className="text-sm font-medium">{r.participant.name}</p>
            <p className="truncate text-xs text-gray-500">{r.participant.role || '역할 미입력'}</p>
            {!r.briefing && <p className="text-[11px] text-amber-600">브리핑 없음</p>}
          </button>
        ))}
      </div>
      {row && (
        <div className="card p-5">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-semibold">{row.participant.name} <span className="text-sm font-normal text-gray-500">· {row.participant.role}</span></h3>
              <p className="text-xs text-gray-500">{row.participant.responsibility || '담당 업무 미입력'}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {row.briefing && <SourceBadge source={row.briefing.source} />}
              {m.can_edit && row.participant.access_token && <button className="btn-secondary" onClick={() => copyLink(row.participant)}>{copied ? '복사됨' : '개인 링크 복사'}</button>}
              {m.can_edit && row.briefing && !draft && <button className="btn-secondary" onClick={() => setDraft(structuredClone(row.briefing!.content))}>수정</button>}
              {m.can_edit && !draft && <button className="btn-secondary" onClick={regenerate} disabled={!!busy}>{busy === 'regen' && <Spinner />}{row.briefing ? '다시 생성' : '브리핑 생성'}</button>}
              {draft && <><button className="btn-secondary" onClick={() => setDraft(null)}>취소</button><button className="btn-primary" onClick={save} disabled={!!busy}>{busy === 'save' && <Spinner />}저장</button></>}
            </div>
          </div>
          {err && <div className="mb-3"><Alert onClose={() => setErr('')}>{err}</Alert></div>}
          {!row.briefing ? <p className="text-sm text-gray-500">아직 개인 브리핑이 없습니다. {m.can_edit && "'브리핑 생성'을 눌러 주세요."}</p> : draft ? (
            <div className="space-y-5">
              <div><label className="label">요약</label><textarea className="input" rows={2} value={draft.focus_summary} onChange={(e) => setDraft({ ...draft, focus_summary: e.target.value })} /></div>
              {SECTIONS.map(([k, t]) => (
                <div key={k}><p className="label">{t}</p><ItemsEditor items={draft[k] as BriefingItem[]} onChange={(v) => setDraft({ ...draft, [k]: v })} /></div>
              ))}
              <div><label className="label">관련 전문 용어 (쉼표로 구분)</label><input className="input" value={draft.related_terms.join(', ')} onChange={(e) => setDraft({ ...draft, related_terms: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} /></div>
            </div>
          ) : (
            <>
              <div className="mb-4"><BasisLegend /></div>
              <PersonalView c={row.briefing.content} />
            </>
          )}
        </div>
      )}
    </div>
  )
}
