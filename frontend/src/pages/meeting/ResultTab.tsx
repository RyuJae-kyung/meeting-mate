import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../../api/client'
import type { MeetingDetail, MeetingResult, Priority, Task } from '../../api/types'
import { Alert, PageLoader, SectionTitle, SourceBadge, Spinner } from '../../components/ui'
import { DueLabel, PriorityBadge, StatusSelect } from '../../components/tasks'
import { fmtDateTime } from '../../lib/format'

interface Row {
  title: string; description: string; assignee_participant_id: number | null; assignee_name: string
  due_date: string; priority: Priority; reminder_enabled: boolean; uncertain: boolean; evidence: string; due_text: string | null
}

function ListEditor({ label, items, onChange, placeholder }: { label: string; items: string[]; onChange: (v: string[]) => void; placeholder: string }) {
  return (
    <div>
      <p className="label">{label}</p>
      <div className="space-y-1.5">
        {items.map((x, i) => (
          <div key={i} className="flex gap-2">
            <input className="input" value={x} placeholder={placeholder} onChange={(e) => onChange(items.map((y, j) => (j === i ? e.target.value : y)))} aria-label={label} />
            <button type="button" className="btn-ghost text-red-600" onClick={() => onChange(items.filter((_, j) => j !== i))}>삭제</button>
          </div>
        ))}
        <button type="button" className="btn-ghost text-indigo-600" onClick={() => onChange([...items, ''])}>+ 추가</button>
      </div>
    </div>
  )
}

function Bullets({ title, items }: { title: string; items: string[] }) {
  return (
    <section>
      <h4 className="mb-1.5 text-sm font-semibold">{title}</h4>
      {items.length ? <ul className="list-inside list-disc space-y-1 text-sm text-gray-800">{items.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="text-sm text-gray-400">없음</p>}
    </section>
  )
}

export default function ResultTab({ m, reload }: { m: MeetingDetail; reload: () => Promise<unknown> }) {
  const [result, setResult] = useState<MeetingResult | null | undefined>(undefined)
  const [tasks, setTasks] = useState<Task[]>([])
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [edit, setEdit] = useState<{ summary: string; decisions: string[]; undecided: string[]; further: string[]; rows: Row[] } | null>(null)
  const [markCompleted, setMarkCompleted] = useState(true)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  async function load() {
    const [r, t] = await Promise.all([api.get<MeetingResult | null>(`/meetings/${m.id}/result`), api.get<Task[]>('/tasks', { params: { meeting_id: m.id } })])
    setResult(r.data); setTasks(t.data)
    if (r.data?.status === 'draft' && m.can_edit) startEdit(r.data)
  }
  useEffect(() => { load().catch((e) => setErr(errorMessage(e))) }, [m.id]) // eslint-disable-line react-hooks/exhaustive-deps

  function startEdit(r: MeetingResult) {
    setEdit({
      summary: r.summary, decisions: [...r.decisions], undecided: [...r.undecided], further: [...r.further_discussion],
      rows: r.draft_tasks.map((t) => ({ title: t.title, description: t.description, assignee_participant_id: t.assignee_participant_id, assignee_name: t.assignee_name,
        due_date: t.due_date ?? '', priority: t.priority, reminder_enabled: true, uncertain: t.uncertain, evidence: t.evidence, due_text: t.due_text })),
    })
  }

  async function analyze() {
    if (text.trim().length < 10 && !file) { setErr('회의 내용을 10자 이상 입력하거나 회의록 파일을 선택해 주세요.'); return }
    if (edit && !confirm('지금 편집 중인 분석 결과가 새 결과로 바뀝니다. 계속할까요?')) return
    setBusy('analyze'); setErr(''); setOk('')
    const fd = new FormData()
    fd.append('text', text)
    if (file) fd.append('file', file)
    try {
      const r = await api.post<MeetingResult>(`/meetings/${m.id}/result/analyze`, fd)
      setResult(r.data); startEdit(r.data)
    } catch (e) { setErr(errorMessage(e)) } finally { setBusy('') }
  }

  async function save() {
    if (!edit) return
    const bad = edit.rows.findIndex((r) => !r.title.trim())
    if (bad >= 0) { setErr(`${bad + 1}번째 업무의 내용을 입력해 주세요.`); return }
    setBusy('confirm'); setErr('')
    try {
      const r = await api.post(`/meetings/${m.id}/result/confirm`, {
        summary: edit.summary, decisions: edit.decisions, undecided: edit.undecided, further_discussion: edit.further, mark_completed: markCompleted,
        tasks: edit.rows.map((x) => ({ title: x.title, description: x.description, assignee_participant_id: x.assignee_participant_id,
          assignee_name: x.assignee_name, due_date: x.due_date || null, priority: x.priority, reminder_enabled: x.reminder_enabled })),
      })
      setOk(`회의 결과를 저장하고 후속 업무 ${r.data.tasks.length}건을 등록했습니다.`)
      setEdit(null); setText(''); setFile(null)
      await Promise.all([load(), reload()])
    } catch (e) { setErr(errorMessage(e)) } finally { setBusy('') }
  }

  async function setStatus(t: Task, status: Task['status']) {
    try { const r = await api.patch<Task>(`/tasks/${t.id}/status`, { status }); setTasks((ts) => ts.map((x) => (x.id === t.id ? r.data : x))) } catch (e) { setErr(errorMessage(e)) }
  }

  const upd = (i: number, patch: Partial<Row>) => setEdit((e) => e && { ...e, rows: e.rows.map((r, j) => (j === i ? { ...r, ...patch } : r)) })

  if (result === undefined) return err ? <Alert>{err}</Alert> : <PageLoader />
  return (
    <div className="space-y-6">
      {err && <Alert onClose={() => setErr('')}>{err}</Alert>}
      {ok && <Alert kind="success" onClose={() => setOk('')}>{ok} <Link to="/tasks" className="font-medium underline">업무 관리로 이동</Link></Alert>}

      {m.can_edit && !edit && (
        <section className="card p-5">
          <SectionTitle>{result ? '회의 내용 다시 분석' : '회의 결과 입력'}</SectionTitle>
          <p className="mb-3 text-sm text-gray-500">회의에서 나온 내용을 붙여 넣거나 회의록 파일(PDF·DOCX·PPTX·TXT)을 올리면 결정 사항과 담당자별 후속 업무를 추출합니다. 추출 결과는 확인·수정한 뒤 저장할 때 업무로 등록됩니다.</p>
          <textarea className="input font-mono text-[13px]" rows={8} value={text} onChange={(e) => setText(e.target.value)} aria-label="회의 내용"
            placeholder={'예)\n1차 연동 범위는 생산 실적과 자재 투입으로 확정했다.\n김개발: API 연동 테스트 11월 20일까지\n이기획님이 다음 주 수요일까지 요구사항 문서 정리\n2차 범위는 보류, 다음 회의에서 재논의'} />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm">
              <button type="button" className="btn-secondary" onClick={() => fileRef.current?.click()}>회의록 파일 선택</button>
              <input ref={fileRef} type="file" accept=".pdf,.docx,.pptx,.txt" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              {file && <span className="text-gray-600">{file.name} <button className="text-xs text-gray-400 hover:text-red-600" onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = '' }}>제거</button></span>}
            </div>
            <button className="btn-primary" onClick={analyze} disabled={busy === 'analyze'}>{busy === 'analyze' && <Spinner />}{busy === 'analyze' ? '분석 중...' : 'AI로 결과 분석'}</button>
          </div>
        </section>
      )}

      {edit && result && (
        <section className="card space-y-5 p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">분석 결과 확인 및 수정</h3>
            <div className="flex items-center gap-2 text-xs text-gray-500"><SourceBadge source={result.source} />{result.source_filename && <span>{result.source_filename}</span>}</div>
          </div>
          <Alert kind="warning">AI가 추출한 담당자와 마감일은 확정된 값이 아닐 수 있습니다. 저장 전에 꼭 확인해 주세요. '확인 필요' 표시는 담당자나 마감일이 불분명한 항목입니다.</Alert>
          <div><label className="label">주요 내용 요약</label><textarea className="input" rows={3} value={edit.summary} onChange={(e) => setEdit({ ...edit, summary: e.target.value })} /></div>
          <div className="grid gap-5 md:grid-cols-3">
            <ListEditor label="최종 결정 사항" items={edit.decisions} onChange={(v) => setEdit({ ...edit, decisions: v })} placeholder="결정 사항" />
            <ListEditor label="미결정 사항" items={edit.undecided} onChange={(v) => setEdit({ ...edit, undecided: v })} placeholder="미결정 사항" />
            <ListEditor label="추가 논의 필요" items={edit.further} onChange={(v) => setEdit({ ...edit, further: v })} placeholder="추가 논의" />
          </div>
          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="label mb-0">후속 업무 ({edit.rows.length})</p>
              <button type="button" className="btn-secondary" onClick={() => setEdit({ ...edit, rows: [...edit.rows, { title: '', description: '', assignee_participant_id: null, assignee_name: '', due_date: '', priority: 'medium', reminder_enabled: true, uncertain: false, evidence: '', due_text: null }] })}>+ 업무 추가</button>
            </div>
            <div className="space-y-3">
              {edit.rows.map((r, i) => (
                <div key={i} className={`rounded-md border p-3 ${r.uncertain ? 'border-amber-300 bg-amber-50/40' : 'border-gray-200'}`}>
                  <div className="grid gap-2 md:grid-cols-[2fr_1.2fr_1fr_0.8fr_auto]">
                    <input className="input" placeholder="업무 내용" value={r.title} onChange={(e) => upd(i, { title: e.target.value })} aria-label="업무 내용" />
                    <select className="input" aria-label="담당자" value={r.assignee_participant_id ?? (r.assignee_name ? `name:${r.assignee_name}` : '')}
                      onChange={(e) => { const v = e.target.value; if (v.startsWith('name:')) return; const p = m.participants.find((x) => String(x.id) === v); upd(i, { assignee_participant_id: p ? p.id : null, assignee_name: p ? p.name : '' }) }}>
                      <option value="">담당자 미지정</option>
                      {m.participants.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.role || '참석자'})</option>)}
                      {!r.assignee_participant_id && r.assignee_name && <option value={`name:${r.assignee_name}`}>{r.assignee_name} (참석자 아님 · 알림 불가)</option>}
                    </select>
                    <input className="input" type="date" value={r.due_date} onChange={(e) => upd(i, { due_date: e.target.value })} aria-label="마감일" />
                    <select className="input" value={r.priority} onChange={(e) => upd(i, { priority: e.target.value as Priority })} aria-label="우선순위">
                      <option value="high">높음</option><option value="medium">보통</option><option value="low">낮음</option>
                    </select>
                    <button type="button" className="btn-ghost text-red-600" onClick={() => setEdit({ ...edit, rows: edit.rows.filter((_, j) => j !== i) })}>삭제</button>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
                    {r.uncertain && <span className="font-medium text-amber-700">확인 필요</span>}
                    {r.due_text && <span>원문 마감 표현: “{r.due_text}”</span>}
                    {r.evidence && <span className="truncate">근거: “{r.evidence}”</span>}
                    <label className="ml-auto flex items-center gap-1.5"><input type="checkbox" checked={r.reminder_enabled} onChange={(e) => upd(i, { reminder_enabled: e.target.checked })} />마감 임박 알림 이메일</label>
                  </div>
                </div>
              ))}
              {!edit.rows.length && <p className="text-sm text-gray-400">추출된 업무가 없습니다. 필요하면 직접 추가하세요.</p>}
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={markCompleted} onChange={(e) => setMarkCompleted(e.target.checked)} />회의 상태를 '진행 완료'로 변경</label>
            <div className="flex gap-2">
              {result.status === 'confirmed' && <button className="btn-secondary" onClick={() => setEdit(null)}>취소</button>}
              <button className="btn-primary" onClick={save} disabled={busy === 'confirm'}>{busy === 'confirm' && <Spinner />}확인 후 저장 · 업무 {edit.rows.length}건 등록</button>
            </div>
          </div>
        </section>
      )}

      {result?.status === 'confirmed' && !edit && (
        <section className="card space-y-4 p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">확정된 회의 결과</h3>
            <span className="text-xs text-gray-500">{fmtDateTime(result.confirmed_at)} 확정</span>
          </div>
          {result.summary && <p className="whitespace-pre-wrap text-sm text-gray-800">{result.summary}</p>}
          <div className="grid gap-5 md:grid-cols-3">
            <Bullets title="최종 결정 사항" items={result.decisions} />
            <Bullets title="미결정 사항" items={result.undecided} />
            <Bullets title="추가 논의 필요" items={result.further_discussion} />
          </div>
        </section>
      )}
      {!result && !m.can_edit && <p className="text-sm text-gray-400">아직 회의 결과가 등록되지 않았습니다.</p>}

      <section>
        <SectionTitle right={<Link to={`/tasks?meeting=${m.id}`} className="text-xs text-indigo-600">업무 관리에서 보기</Link>}>이 회의의 후속 업무 ({tasks.length})</SectionTitle>
        {tasks.length ? (
          <div className="card divide-y">
            {tasks.map((t) => (
              <div key={t.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                <PriorityBadge p={t.priority} />
                <p className={`min-w-0 flex-1 truncate text-sm ${t.status === 'done' ? 'text-gray-400 line-through' : ''}`}>{t.title}</p>
                <span className="text-xs text-gray-600">{t.assignee_name || '미지정'}</span>
                <DueLabel due={t.due_date} done={t.status === 'done'} />
                <StatusSelect value={t.status} disabled={!t.can_update_status} onChange={(s) => setStatus(t, s)} />
              </div>
            ))}
          </div>
        ) : <p className="text-sm text-gray-400">등록된 후속 업무가 없습니다.</p>}
      </section>
    </div>
  )
}
