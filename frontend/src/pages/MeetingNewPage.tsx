import { useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { GenerateResult, Material, MeetingDetail } from '../api/types'
import MeetingFields, { emptyMeetingForm, formToPayload, type MeetingForm } from '../components/MeetingFields'
import { Alert, Spinner } from '../components/ui'
import { fmtSize } from '../lib/format'

interface PRow { name: string; email: string; role: string; responsibility: string }
const ROLE_PRESETS = ['개발 담당자', '기획 담당자', '관리자', '영업 담당자', '디자이너', 'QA 담당자']
const ACCEPT = '.pdf,.docx,.pptx,.txt'
const MAX_MB = 20

export default function MeetingNewPage() {
  const nav = useNavigate()
  const [f, setF] = useState<MeetingForm>(emptyMeetingForm)
  const [people, setPeople] = useState<PRow[]>([{ name: '', email: '', role: '', responsibility: '' }])
  const [files, setFiles] = useState<File[]>([])
  const [autoBrief, setAutoBrief] = useState(true)
  const [err, setErr] = useState('')
  const [step, setStep] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  function addFiles(list: FileList | null) {
    if (!list) return
    const bad: string[] = []
    const ok: File[] = []
    for (const file of Array.from(list)) {
      const ext = file.name.split('.').pop()?.toLowerCase()
      if (!['pdf', 'docx', 'pptx', 'txt'].includes(ext || '')) bad.push(`${file.name}: 지원하지 않는 형식`)
      else if (file.size > MAX_MB * 1024 * 1024) bad.push(`${file.name}: ${MAX_MB}MB 초과`)
      else ok.push(file)
    }
    setFiles((prev) => [...prev, ...ok].slice(0, 10))
    setErr(bad.join(' / '))
    if (fileRef.current) fileRef.current.value = ''
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setErr('')
    const participants = people.filter((p) => p.name.trim() || p.email.trim())
    if (participants.some((p) => !p.name.trim() || !p.email.trim())) { setErr('참석자의 이름과 이메일을 모두 입력해 주세요.'); return }
    let meetingId: number | null = null
    try {
      setStep('회의 등록 중...')
      const r = await api.post<MeetingDetail>('/meetings', { ...formToPayload(f), participants })
      meetingId = r.data.id
      const warns: string[] = []
      if (files.length) {
        setStep(`자료 ${files.length}개 업로드 및 텍스트 추출 중...`)
        const fd = new FormData()
        files.forEach((file) => fd.append('files', file))
        const up = await api.post<Material[]>(`/meetings/${meetingId}/materials`, fd)
        up.data.filter((m) => m.status === 'failed').forEach((m) => warns.push(`${m.original_filename}: ${m.error}`))
      }
      if (autoBrief) {
        setStep('AI 브리핑·전문 용어·참석자별 브리핑 생성 중... (최대 1~2분)')
        const g = await api.post<GenerateResult>(`/meetings/${meetingId}/briefings/generate`)
        warns.push(...g.data.warnings)
      }
      nav(`/meetings/${meetingId}${autoBrief ? '?tab=briefing' : ''}`, { state: { warnings: warns } })
    } catch (e) {
      const msg = errorMessage(e)
      if (meetingId) nav(`/meetings/${meetingId}`, { state: { warnings: [`회의는 등록되었지만 후속 단계에서 오류가 발생했습니다: ${msg}`] } })
      else { setErr(msg); setStep('') }
    }
  }

  const busy = !!step
  return (
    <form onSubmit={submit} className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">새 회의 만들기</h1>
        <p className="text-sm text-gray-500">회의 정보와 자료를 입력하면 AI가 참석자별 사전 브리핑을 만들어 드립니다.</p>
      </div>
      {err && <Alert onClose={() => setErr('')}>{err}</Alert>}

      <section className="card p-5">
        <h2 className="mb-4 text-sm font-semibold">회의 정보</h2>
        <MeetingFields f={f} set={setF} />
      </section>

      <section className="card p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold">참석자 및 역할</h2>
          <button type="button" className="btn-secondary" onClick={() => setPeople([...people, { name: '', email: '', role: '', responsibility: '' }])}>+ 참석자 추가</button>
        </div>
        <datalist id="roles">{ROLE_PRESETS.map((r) => <option key={r} value={r} />)}</datalist>
        <div className="space-y-3">
          {people.map((p, i) => (
            <div key={i} className="grid gap-2 rounded-md border border-gray-100 bg-gray-50/50 p-3 md:grid-cols-[1fr_1.3fr_1fr_1.6fr_auto]">
              <input className="input" placeholder="이름" value={p.name} onChange={(e) => setPeople(people.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} aria-label="참석자 이름" />
              <input className="input" type="email" placeholder="이메일" value={p.email} onChange={(e) => setPeople(people.map((x, j) => j === i ? { ...x, email: e.target.value } : x))} aria-label="참석자 이메일" />
              <input className="input" list="roles" placeholder="역할 (예: 개발 담당자)" value={p.role} onChange={(e) => setPeople(people.map((x, j) => j === i ? { ...x, role: e.target.value } : x))} aria-label="역할" />
              <input className="input" placeholder="담당 업무 (예: API 연동 개발)" value={p.responsibility} onChange={(e) => setPeople(people.map((x, j) => j === i ? { ...x, responsibility: e.target.value } : x))} aria-label="담당 업무" />
              <button type="button" className="btn-ghost text-gray-400" onClick={() => setPeople(people.filter((_, j) => j !== i))} aria-label="참석자 삭제">삭제</button>
            </div>
          ))}
          {!people.length && <p className="text-sm text-gray-400">참석자가 없으면 참석자별 브리핑과 이메일 발송을 할 수 없습니다.</p>}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="mb-1 text-sm font-semibold">회의 자료</h2>
        <p className="mb-3 text-xs text-gray-500">PDF, DOCX, PPTX, TXT · 파일당 최대 {MAX_MB}MB · 최대 10개</p>
        <label
          className="flex cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed border-gray-300 px-4 py-6 text-sm text-gray-500 hover:border-indigo-400"
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer.files) }}>
          <span>파일을 끌어 놓거나 <span className="font-medium text-indigo-600">클릭하여 선택</span></span>
          <input ref={fileRef} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => addFiles(e.target.files)} />
        </label>
        {files.length > 0 && (
          <ul className="mt-3 divide-y rounded-md border">
            {files.map((file, i) => (
              <li key={i} className="flex items-center justify-between px-3 py-2 text-sm">
                <span className="truncate">{file.name} <span className="text-xs text-gray-400">{fmtSize(file.size)}</span></span>
                <button type="button" className="text-xs text-gray-400 hover:text-red-600" onClick={() => setFiles(files.filter((_, j) => j !== i))}>제거</button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={autoBrief} onChange={(e) => setAutoBrief(e.target.checked)} className="rounded border-gray-300" />
          등록 후 바로 AI 브리핑 생성
        </label>
        <div className="flex items-center gap-3">
          {busy && <span className="flex items-center gap-2 text-sm text-gray-500"><Spinner />{step}</span>}
          <button className="btn-primary px-4 py-2" disabled={busy}>{autoBrief ? '회의 등록 및 브리핑 생성' : '회의 등록'}</button>
        </div>
      </div>
    </form>
  )
}
