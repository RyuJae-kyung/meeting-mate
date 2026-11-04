export interface MeetingForm {
  title: string; purpose: string; start: string; end: string; location: string; online_url: string; agenda: string
}
export const emptyMeetingForm: MeetingForm = { title: '', purpose: '', start: '', end: '', location: '', online_url: '', agenda: '' }

export default function MeetingFields({ f, set }: { f: MeetingForm; set: (f: MeetingForm) => void }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="md:col-span-2">
        <label className="label" htmlFor="title">회의 제목 *</label>
        <input id="title" className="input" required maxLength={200} value={f.title} onChange={(e) => set({ ...f, title: e.target.value })} placeholder="예: MES-ERP 연동 프로젝트 킥오프" />
      </div>
      <div className="md:col-span-2">
        <label className="label" htmlFor="purpose">회의 목적</label>
        <textarea id="purpose" className="input" rows={2} value={f.purpose} onChange={(e) => set({ ...f, purpose: e.target.value })} placeholder="이 회의에서 달성하려는 목표" />
      </div>
      <div>
        <label className="label" htmlFor="start">시작 일시 *</label>
        <input id="start" className="input" type="datetime-local" required value={f.start} onChange={(e) => set({ ...f, start: e.target.value })} />
      </div>
      <div>
        <label className="label" htmlFor="end">종료 일시</label>
        <input id="end" className="input" type="datetime-local" value={f.end} min={f.start || undefined} onChange={(e) => set({ ...f, end: e.target.value })} />
      </div>
      <div>
        <label className="label" htmlFor="loc">장소</label>
        <input id="loc" className="input" value={f.location} onChange={(e) => set({ ...f, location: e.target.value })} placeholder="예: 본사 3층 대회의실" />
      </div>
      <div>
        <label className="label" htmlFor="url">온라인 회의 링크</label>
        <input id="url" className="input" type="url" value={f.online_url} onChange={(e) => set({ ...f, online_url: e.target.value })} placeholder="https://" />
      </div>
      <div className="md:col-span-2">
        <label className="label" htmlFor="agenda">회의 안건 (한 줄에 하나씩)</label>
        <textarea id="agenda" className="input font-mono text-[13px]" rows={4} value={f.agenda} onChange={(e) => set({ ...f, agenda: e.target.value })} placeholder={'연동 범위 확정\nAPI 개발 일정\n예산 및 리스크 검토'} />
      </div>
    </div>
  )
}

export function formToPayload(f: MeetingForm) {
  return {
    title: f.title.trim(),
    purpose: f.purpose.trim(),
    start_at: new Date(f.start).toISOString(),
    end_at: f.end ? new Date(f.end).toISOString() : null,
    location: f.location.trim() || null,
    online_url: f.online_url.trim() || null,
    agenda: f.agenda,
  }
}
