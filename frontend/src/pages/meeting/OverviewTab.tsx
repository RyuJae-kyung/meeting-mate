import { useState, type FormEvent } from 'react'
import { api, errorMessage } from '../../api/client'
import type { MeetingDetail, MeetingStatus, Participant } from '../../api/types'
import MeetingFields, { formToPayload, type MeetingForm } from '../../components/MeetingFields'
import { Alert, Modal, SectionTitle, Spinner } from '../../components/ui'
import { isoToLocalInput } from '../../lib/format'

const STATUS_OPTS: [MeetingStatus, string][] = [['scheduled', '예정'], ['ready', '준비 완료'], ['completed', '진행 완료']]
type PForm = { name: string; email: string; role: string; responsibility: string }

export default function OverviewTab({ m, reload, onDeleted }: { m: MeetingDetail; reload: () => Promise<unknown>; onDeleted: () => void }) {
  const [editing, setEditing] = useState(false)
  const [f, setF] = useState<MeetingForm | null>(null)
  const [pEdit, setPEdit] = useState<{ id: number | null; f: PForm } | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  function openEdit() {
    setF({ title: m.title, purpose: m.purpose, start: isoToLocalInput(m.start_at), end: isoToLocalInput(m.end_at), location: m.location || '', online_url: m.online_url || '', agenda: m.agenda })
    setEditing(true)
  }
  async function save(e: FormEvent) {
    e.preventDefault()
    if (!f) return
    setBusy(true); setErr('')
    try { await api.put(`/meetings/${m.id}`, formToPayload(f)); await reload(); setEditing(false) } catch (e) { setErr(errorMessage(e)) } finally { setBusy(false) }
  }
  async function setStatus(status: MeetingStatus) {
    try { await api.patch(`/meetings/${m.id}/status`, { status }); await reload() } catch (e) { setErr(errorMessage(e)) }
  }
  async function remove() {
    if (!confirm(`'${m.title}' 회의와 모든 자료·브리핑·발송 기록을 삭제할까요? 되돌릴 수 없습니다.`)) return
    try { await api.delete(`/meetings/${m.id}`); onDeleted() } catch (e) { setErr(errorMessage(e)) }
  }
  async function saveParticipant(e: FormEvent) {
    e.preventDefault()
    if (!pEdit) return
    setBusy(true); setErr('')
    try {
      if (pEdit.id) await api.put(`/participants/${pEdit.id}`, pEdit.f)
      else await api.post(`/meetings/${m.id}/participants`, pEdit.f)
      await reload(); setPEdit(null)
    } catch (e) { setErr(errorMessage(e)) } finally { setBusy(false) }
  }
  async function removeParticipant(p: Participant) {
    if (!confirm(`${p.name}님을 참석자에서 제외할까요? 개인 브리핑도 함께 삭제됩니다.`)) return
    try { await api.delete(`/participants/${p.id}`); await reload() } catch (e) { setErr(errorMessage(e)) }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        {err && <Alert onClose={() => setErr('')}>{err}</Alert>}
        <section className="card p-5">
          <SectionTitle right={m.can_edit && <button className="btn-secondary" onClick={openEdit}>수정</button>}>회의 정보</SectionTitle>
          <dl className="grid gap-3 text-sm sm:grid-cols-[100px_1fr]">
            <dt className="text-gray-500">목적</dt><dd className="whitespace-pre-wrap">{m.purpose || <span className="text-gray-400">미입력</span>}</dd>
            <dt className="text-gray-500">장소</dt><dd>{m.location || <span className="text-gray-400">미입력</span>}</dd>
            <dt className="text-gray-500">온라인 링크</dt><dd>{m.online_url ? <a href={m.online_url} target="_blank" rel="noreferrer" className="break-all text-indigo-600 hover:underline">{m.online_url}</a> : <span className="text-gray-400">없음</span>}</dd>
            <dt className="text-gray-500">안건</dt>
            <dd>{m.agenda_items.length ? <ol className="list-inside list-decimal space-y-1">{m.agenda_items.map((a, i) => <li key={i}>{a}</li>)}</ol> : <span className="text-gray-400">미입력</span>}</dd>
          </dl>
        </section>

        <section className="card p-5">
          <SectionTitle right={m.can_edit && <button className="btn-secondary" onClick={() => setPEdit({ id: null, f: { name: '', email: '', role: '', responsibility: '' } })}>+ 참석자</button>}>
            참석자 ({m.participants.length})
          </SectionTitle>
          {m.participants.length ? (
            <div className="divide-y">
              {m.participants.map((p) => (
                <div key={p.id} className="flex items-start justify-between gap-3 py-2.5">
                  <div className="min-w-0 text-sm">
                    <p className="font-medium">{p.name} <span className="font-normal text-gray-500">· {p.role || '역할 미입력'}</span></p>
                    <p className="text-xs text-gray-500">{p.email}{p.responsibility ? ` · ${p.responsibility}` : ''}</p>
                  </div>
                  {m.can_edit && (
                    <div className="flex shrink-0 gap-1">
                      <button className="btn-ghost text-xs" onClick={() => setPEdit({ id: p.id, f: { name: p.name, email: p.email, role: p.role, responsibility: p.responsibility } })}>수정</button>
                      <button className="btn-ghost text-xs text-red-600" onClick={() => removeParticipant(p)}>삭제</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : <p className="text-sm text-gray-400">참석자가 없습니다.</p>}
        </section>
      </div>

      <aside className="space-y-4">
        <section className="card p-5">
          <SectionTitle>회의 상태</SectionTitle>
          {m.can_edit ? (
            <div className="flex flex-col gap-1">
              {STATUS_OPTS.map(([v, l]) => (
                <label key={v} className="flex items-center gap-2 text-sm"><input type="radio" name="status" checked={m.status === v} onChange={() => setStatus(v)} />{l}</label>
              ))}
              <p className="mt-2 text-xs text-gray-500">AI 브리핑을 생성하면 자동으로 '준비 완료'가 됩니다.</p>
            </div>
          ) : <p className="text-sm">{STATUS_OPTS.find(([v]) => v === m.status)?.[1]}</p>}
        </section>
        <section className="card p-5 text-sm">
          <SectionTitle>준비 현황</SectionTitle>
          <ul className="space-y-1.5">
            <li>{m.material_count > 0 ? '✓' : '○'} 회의 자료 {m.material_count}개</li>
            <li>{m.has_briefing ? '✓' : '○'} AI 사전 브리핑</li>
            <li>{m.participants.length > 0 ? '✓' : '○'} 참석자 {m.participants.length}명</li>
          </ul>
        </section>
        {m.can_edit && <button className="btn-danger w-full" onClick={remove}>회의 삭제</button>}
      </aside>

      <Modal open={editing} title="회의 정보 수정" onClose={() => setEditing(false)} wide
        footer={<><button className="btn-secondary" onClick={() => setEditing(false)}>취소</button><button className="btn-primary" form="meeting-edit" disabled={busy}>{busy && <Spinner />}저장</button></>}>
        {f && <form id="meeting-edit" onSubmit={save}><MeetingFields f={f} set={setF} /></form>}
        <p className="mt-3 text-xs text-gray-500">회의 정보를 바꾼 뒤에는 'AI 브리핑 다시 생성'으로 브리핑에 반영할 수 있습니다.</p>
      </Modal>

      <Modal open={!!pEdit} title={pEdit?.id ? '참석자 수정' : '참석자 추가'} onClose={() => setPEdit(null)}
        footer={<><button className="btn-secondary" onClick={() => setPEdit(null)}>취소</button><button className="btn-primary" form="p-edit" disabled={busy}>{busy && <Spinner />}저장</button></>}>
        {pEdit && (
          <form id="p-edit" onSubmit={saveParticipant} className="space-y-3">
            <div><label className="label">이름 *</label><input className="input" required value={pEdit.f.name} onChange={(e) => setPEdit({ ...pEdit, f: { ...pEdit.f, name: e.target.value } })} /></div>
            <div><label className="label">이메일 *</label><input className="input" type="email" required value={pEdit.f.email} onChange={(e) => setPEdit({ ...pEdit, f: { ...pEdit.f, email: e.target.value } })} /></div>
            <div><label className="label">역할</label><input className="input" placeholder="예: 개발 담당자" value={pEdit.f.role} onChange={(e) => setPEdit({ ...pEdit, f: { ...pEdit.f, role: e.target.value } })} /></div>
            <div><label className="label">담당 업무</label><textarea className="input" rows={2} value={pEdit.f.responsibility} onChange={(e) => setPEdit({ ...pEdit, f: { ...pEdit.f, responsibility: e.target.value } })} /></div>
            {!pEdit.id && <p className="text-xs text-gray-500">새 참석자의 개인 브리핑은 '참석자별 브리핑' 탭에서 생성할 수 있습니다.</p>}
          </form>
        )}
      </Modal>
    </div>
  )
}
