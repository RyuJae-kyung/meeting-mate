import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { MeetingDetail, MeetingListItem, Priority, Task } from '../api/types'
import { DueLabel, PriorityBadge, StatusSelect } from '../components/tasks'
import { Alert, EmptyState, Modal, PageLoader, Spinner } from '../components/ui'
import { useAuth } from '../lib/auth'
import { fmtDateTime } from '../lib/format'

type Group = 'none' | 'assignee' | 'meeting'

interface EditState {
  id: number | null; meeting_id: number; title: string; description: string; assignee_participant_id: number | null
  assignee_name: string; due_date: string; priority: Priority; reminder_enabled: boolean
}

export default function TasksPage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const scope = params.get('scope') === 'mine' ? 'mine' : 'all'
  const status = params.get('status') ?? 'open'
  const due = params.get('due') ?? ''
  const meetingId = params.get('meeting') ?? ''
  const [assignee, setAssignee] = useState('')
  const [group, setGroup] = useState<Group>('assignee')
  const [tasks, setTasks] = useState<Task[] | null>(null)
  const [meetings, setMeetings] = useState<MeetingListItem[]>([])
  const [edit, setEdit] = useState<EditState | null>(null)
  const [editMeeting, setEditMeeting] = useState<MeetingDetail | null>(null)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')

  const set = (k: string, v: string) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p, { replace: true }) }

  const load = useCallback(() =>
    api.get<Task[]>('/tasks', { params: { scope, status: status === 'all' ? undefined : status, due: due || undefined, meeting_id: meetingId || undefined } })
      .then((r) => setTasks(r.data)).catch((e) => setErr(errorMessage(e))), [scope, status, due, meetingId])
  useEffect(() => { load() }, [load])
  useEffect(() => { api.get<MeetingListItem[]>('/meetings').then((r) => setMeetings(r.data)).catch(() => {}) }, [])

  // 업무 추가는 내가 만든 회의(관리자는 전체)에서만 가능
  const editable = meetings.filter((m) => user?.role === 'admin' || m.owner_id === user?.id)
  const assignees = useMemo(() => [...new Set((tasks ?? []).map((t) => t.assignee_name || '미지정'))].sort(), [tasks])
  const shown = (tasks ?? []).filter((t) => !assignee || (t.assignee_name || '미지정') === assignee)
  const groups = useMemo(() => {
    if (group === 'none') return [['', shown]] as [string, Task[]][]
    const map = new Map<string, Task[]>()
    for (const t of shown) {
      const k = group === 'assignee' ? t.assignee_name || '미지정' : t.meeting_title
      map.set(k, [...(map.get(k) ?? []), t])
    }
    return [...map.entries()]
  }, [shown, group])

  async function setStatus(t: Task, s: Task['status']) {
    try { const r = await api.patch<Task>(`/tasks/${t.id}/status`, { status: s }); setTasks((ts) => ts!.map((x) => (x.id === t.id ? r.data : x))) } catch (e) { setErr(errorMessage(e)) }
  }
  async function openEdit(t: Task | null) {
    const preferred = editable.find((m) => String(m.id) === meetingId) ?? editable[0]
    const mid = t?.meeting_id ?? preferred?.id
    if (!mid) { setErr('업무를 추가할 수 있는 회의(내가 만든 회의)가 없습니다.'); return }
    try {
      setEditMeeting((await api.get<MeetingDetail>(`/meetings/${mid}`)).data)
      setEdit(t ? { id: t.id, meeting_id: t.meeting_id, title: t.title, description: t.description, assignee_participant_id: t.assignee_participant_id, assignee_name: t.assignee_name, due_date: t.due_date ?? '', priority: t.priority, reminder_enabled: t.reminder_enabled }
        : { id: null, meeting_id: mid, title: '', description: '', assignee_participant_id: null, assignee_name: '', due_date: '', priority: 'medium', reminder_enabled: true })
    } catch (e) { setErr(errorMessage(e)) }
  }
  async function changeEditMeeting(mid: number) {
    try { setEditMeeting((await api.get<MeetingDetail>(`/meetings/${mid}`)).data); setEdit((e) => e && { ...e, meeting_id: mid, assignee_participant_id: null, assignee_name: '' }) } catch (e) { setErr(errorMessage(e)) }
  }
  async function save(e: FormEvent) {
    e.preventDefault()
    if (!edit) return
    setBusy('save'); setErr('')
    const body = { title: edit.title, description: edit.description, assignee_participant_id: edit.assignee_participant_id, assignee_name: edit.assignee_name,
      due_date: edit.due_date || null, priority: edit.priority, reminder_enabled: edit.reminder_enabled }
    try {
      if (edit.id) await api.put(`/tasks/${edit.id}`, body)
      else await api.post(`/meetings/${edit.meeting_id}/tasks`, body)
      setEdit(null); await load()
    } catch (e) { setErr(errorMessage(e)) } finally { setBusy('') }
  }
  async function remove(t: Task) {
    if (!confirm(`'${t.title}' 업무를 삭제할까요?`)) return
    try { await api.delete(`/tasks/${t.id}`); setTasks((ts) => ts!.filter((x) => x.id !== t.id)) } catch (e) { setErr(errorMessage(e)) }
  }
  async function remind(t: Task) {
    if (!confirm(`${t.assignee_name}(${t.assignee_email})님에게 '${t.title}' 업무 알림 이메일을 지금 보낼까요?`)) return
    setBusy(`r-${t.id}`); setErr(''); setOk('')
    try {
      const r = await api.post(`/tasks/${t.id}/remind`)
      if (r.data.status === 'sent') setOk(`알림을 보냈습니다${r.data.provider === 'mock' ? ' (Mock 모드: 실제 발송 안 됨)' : ''}.`)
      else setErr(`알림 발송 실패: ${r.data.error} — 회의 상세의 '이메일 발송' 내역에서 재시도할 수 있습니다.`)
      await load()
    } catch (e) { setErr(errorMessage(e)) } finally { setBusy('') }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">업무 관리</h1>
        <button className="btn-primary" onClick={() => openEdit(null)} disabled={!editable.length}>+ 업무 추가</button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border border-gray-200 bg-white p-0.5">
          {[['all', '전체 업무'], ['mine', '내 업무']].map(([v, l]) => (
            <button key={v} onClick={() => set('scope', v === 'all' ? '' : v)} className={`rounded px-3 py-1 text-sm ${scope === v ? 'bg-gray-100 font-medium' : 'text-gray-500'}`}>{l}</button>
          ))}
        </div>
        <select className="input w-auto" value={status} onChange={(e) => set('status', e.target.value === 'open' ? '' : e.target.value)} aria-label="상태">
          <option value="open">미완료 (대기+진행 중)</option><option value="todo">대기</option><option value="in_progress">진행 중</option><option value="done">완료</option><option value="all">전체 상태</option>
        </select>
        <select className="input w-auto" value={due} onChange={(e) => set('due', e.target.value)} aria-label="마감">
          <option value="">마감일 전체</option><option value="soon">마감 임박 (3일 이내)</option><option value="overdue">기한 지남</option>
        </select>
        <select className="input w-auto max-w-[14rem]" value={meetingId} onChange={(e) => set('meeting', e.target.value)} aria-label="회의">
          <option value="">모든 회의</option>
          {meetings.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
        </select>
        <select className="input w-auto" value={assignee} onChange={(e) => setAssignee(e.target.value)} aria-label="담당자">
          <option value="">모든 담당자</option>
          {assignees.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select className="input w-auto" value={group} onChange={(e) => setGroup(e.target.value as Group)} aria-label="묶어 보기">
          <option value="assignee">담당자별 보기</option><option value="meeting">회의별 보기</option><option value="none">목록 보기</option>
        </select>
      </div>

      {err && <Alert onClose={() => setErr('')}>{err}</Alert>}
      {ok && <Alert kind="success" onClose={() => setOk('')}>{ok}</Alert>}

      {!tasks ? <PageLoader /> : !shown.length ? (
        <EmptyState title="조건에 맞는 업무가 없습니다" desc="회의 상세의 '회의 결과·후속 업무' 탭에서 회의 내용을 분석하면 업무가 자동으로 등록됩니다." />
      ) : (
        <div className="space-y-5">
          {groups.map(([name, list]) => (
            <section key={name || 'all'}>
              {name && <h2 className="mb-2 text-sm font-semibold">{name} <span className="font-normal text-gray-400">· {list.filter((t) => t.status !== 'done').length}건 미완료 / {list.length}건</span></h2>}
              <div className="card divide-y">
                {list.map((t) => (
                  <div key={t.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center">
                    <div className="flex min-w-0 flex-1 items-start gap-2">
                      <PriorityBadge p={t.priority} />
                      <div className="min-w-0">
                        <p className={`text-sm font-medium ${t.status === 'done' ? 'text-gray-400 line-through' : ''}`}>{t.title}</p>
                        <p className="truncate text-xs text-gray-500">
                          <Link to={`/meetings/${t.meeting_id}?tab=result`} className="hover:text-indigo-600 hover:underline">{t.meeting_title}</Link>
                          {group !== 'assignee' && ` · ${t.assignee_name || '담당자 미지정'}`}
                          {t.description && ` · ${t.description}`}
                          {t.reminder_sent_at && ` · 알림 발송 ${fmtDateTime(t.reminder_sent_at)}`}
                          {!t.assignee_email && t.assignee_name && ' · 참석자 아님(알림 불가)'}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <DueLabel due={t.due_date} done={t.status === 'done'} />
                      <StatusSelect value={t.status} disabled={!t.can_update_status} onChange={(s) => setStatus(t, s)} />
                      {t.can_edit && (
                        <div className="flex gap-0.5">
                          {t.assignee_email && t.status !== 'done' && <button className="btn-ghost px-2 text-xs" onClick={() => remind(t)} disabled={!!busy}>{busy === `r-${t.id}` && <Spinner className="h-3 w-3" />}알림</button>}
                          <button className="btn-ghost px-2 text-xs" onClick={() => openEdit(t)}>수정</button>
                          <button className="btn-ghost px-2 text-xs text-red-600" onClick={() => remove(t)}>삭제</button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <Modal open={!!edit} title={edit?.id ? '업무 수정' : '업무 추가'} onClose={() => setEdit(null)}
        footer={<><button className="btn-secondary" onClick={() => setEdit(null)}>취소</button><button className="btn-primary" form="task-edit" disabled={busy === 'save'}>{busy === 'save' && <Spinner />}저장</button></>}>
        {edit && (
          <form id="task-edit" onSubmit={save} className="space-y-3">
            {!edit.id && (
              <div><label className="label">회의</label>
                <select className="input" value={edit.meeting_id} onChange={(e) => changeEditMeeting(Number(e.target.value))}>
                  {editable.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
                </select>
              </div>
            )}
            <div><label className="label">업무 내용 *</label><input className="input" required maxLength={300} value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></div>
            <div><label className="label">설명</label><textarea className="input" rows={2} value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div><label className="label">담당자</label>
                <select className="input" value={edit.assignee_participant_id ?? ''} onChange={(e) => { const p = editMeeting?.participants.find((x) => String(x.id) === e.target.value); setEdit({ ...edit, assignee_participant_id: p?.id ?? null, assignee_name: p?.name ?? '' }) }}>
                  <option value="">{!edit.assignee_participant_id && edit.assignee_name ? `${edit.assignee_name} (참석자 아님)` : '미지정'}</option>
                  {editMeeting?.participants.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.role || '참석자'})</option>)}
                </select>
              </div>
              <div><label className="label">마감일</label><input className="input" type="date" value={edit.due_date} onChange={(e) => setEdit({ ...edit, due_date: e.target.value })} /></div>
              <div><label className="label">우선순위</label>
                <select className="input" value={edit.priority} onChange={(e) => setEdit({ ...edit, priority: e.target.value as Priority })}>
                  <option value="high">높음</option><option value="medium">보통</option><option value="low">낮음</option>
                </select>
              </div>
              <label className="mt-6 flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.reminder_enabled} onChange={(e) => setEdit({ ...edit, reminder_enabled: e.target.checked })} />마감 임박 알림 이메일</label>
            </div>
            {edit.id && <p className="text-xs text-gray-500">마감일을 바꾸면 새 마감일 기준으로 알림이 다시 발송될 수 있습니다.</p>}
          </form>
        )}
      </Modal>
    </div>
  )
}
