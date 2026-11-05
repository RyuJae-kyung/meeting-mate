import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api, errorMessage } from '../../api/client'
import type { MeetingDetail, Question } from '../../api/types'
import { Alert, PageLoader, SourceBadge, Spinner } from '../../components/ui'

const EXAMPLES = [
  '이번 회의에서 가장 중요한 안건은 무엇인가요?',
  '회의에서 결정해야 할 사항은 무엇인가요?',
  '이 내용과 관련된 위험 요소는 무엇인가요?',
  '내 역할에서 어떤 부분을 준비해야 하나요?',
]
const GROUNDED: Record<Question['grounded'], [string, string]> = {
  materials: ['자료 근거', 'bg-teal-50 text-teal-700'],
  partial: ['자료 + 일반 지식', 'bg-violet-50 text-violet-700'],
  none: ['자료에서 근거 없음', 'bg-amber-50 text-amber-700'],
}

function Answer({ q, onDelete }: { q: Question; onDelete: () => void }) {
  const [label, cls] = GROUNDED[q.grounded]
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white">{q.question}</div>
      </div>
      <div className="card max-w-[92%] space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>{label}</span>
          <SourceBadge source={q.source} />
          <button className="ml-auto text-xs text-gray-400 hover:text-red-600" onClick={onDelete}>삭제</button>
        </div>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">{q.answer}</p>
        {q.citations.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-semibold text-gray-500">참고한 자료</p>
            <ul className="space-y-1.5">
              {q.citations.map((c, i) => (
                <li key={i} className="border-l-2 border-teal-200 pl-2 text-xs text-gray-600">
                  <span className="font-medium text-gray-700">{c.file}{c.loc ? ` · ${c.loc}` : ''}</span>
                  {c.quote && <span className="block text-gray-500">“{c.quote}”</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {q.general_knowledge && (
          <div className="rounded-md bg-gray-50 px-3 py-2 text-xs text-gray-600">
            <p className="mb-0.5 font-semibold text-gray-500">일반 지식 (업로드 자료에 근거하지 않은 설명)</p>
            <p className="whitespace-pre-wrap">{q.general_knowledge}</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default function QATab({ m }: { m: MeetingDetail }) {
  const [items, setItems] = useState<Question[] | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { api.get<Question[]>(`/meetings/${m.id}/questions`).then((r) => setItems(r.data)).catch((e) => setErr(errorMessage(e))) }, [m.id])
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [items?.length, busy])

  async function ask(question: string) {
    if (question.trim().length < 2 || busy) return
    setBusy(true); setErr('')
    try {
      const r = await api.post<Question>(`/meetings/${m.id}/questions`, { question: question.trim() })
      setItems((xs) => [...(xs ?? []), r.data]); setText('')
    } catch (e) { setErr(errorMessage(e)) } finally { setBusy(false) }
  }
  async function remove(id: number) {
    try { await api.delete(`/questions/${id}`); setItems((xs) => xs!.filter((x) => x.id !== id)) } catch (e) { setErr(errorMessage(e)) }
  }
  function submit(e: FormEvent) { e.preventDefault(); ask(text) }

  if (!items) return err ? <Alert>{err}</Alert> : <PageLoader />
  const processed = m.materials.filter((x) => x.status === 'processed').length
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <p className="text-sm text-gray-500">
        업로드된 자료 {processed}개와 생성된 브리핑을 근거로 답합니다. 자료에서 근거를 찾지 못하면 그렇다고 표시하고, 일반 지식으로 보충한 설명은 따로 구분합니다.
      </p>
      {processed === 0 && <Alert kind="info">분석된 자료가 없어 대부분의 질문에 '자료에서 근거 없음'으로 답하게 됩니다. '업로드 자료' 탭에서 자료를 추가하세요.</Alert>}
      {err && <Alert onClose={() => setErr('')}>{err}</Alert>}
      <div className="space-y-5">
        {items.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-300 p-5">
            <p className="mb-3 text-sm font-medium text-gray-700">이런 질문을 해 보세요</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((q) => <button key={q} className="rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-700 hover:border-indigo-300" onClick={() => ask(q)} disabled={busy}>{q}</button>)}
            </div>
          </div>
        )}
        {items.map((q) => <Answer key={q.id} q={q} onDelete={() => remove(q.id)} />)}
        {busy && <div className="flex items-center gap-2 text-sm text-gray-500"><Spinner />자료를 찾아 답변을 작성하는 중...</div>}
        <div ref={endRef} />
      </div>
      <form onSubmit={submit} className="sticky bottom-0 flex gap-2 border-t bg-gray-50 py-3">
        <input className="input" placeholder="회의 자료에 대해 질문하세요" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} aria-label="질문" />
        <button className="btn-primary shrink-0" disabled={busy || text.trim().length < 2}>질문하기</button>
      </form>
    </div>
  )
}
