import type { Priority, TaskStatus } from '../api/types'

export const PRIORITY: Record<Priority, [string, string]> = {
  high: ['높음', 'bg-red-50 text-red-700'], medium: ['보통', 'bg-gray-100 text-gray-700'], low: ['낮음', 'bg-slate-50 text-slate-500'],
}
export const TASK_STATUS: Record<TaskStatus, [string, string]> = {
  todo: ['대기', 'bg-gray-100 text-gray-700'], in_progress: ['진행 중', 'bg-indigo-50 text-indigo-700'], done: ['완료', 'bg-emerald-50 text-emerald-700'],
}

export function PriorityBadge({ p }: { p: Priority }) {
  const [l, c] = PRIORITY[p] ?? PRIORITY.medium
  return <span className={`inline-flex shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium ${c}`}>{l}</span>
}

/** 마감일 D-day 표시. 기한 지남은 빨간색, 3일 이내는 주황색 */
export function DueLabel({ due, done }: { due: string | null; done?: boolean }) {
  if (!due) return <span className="text-xs text-gray-400">마감일 없음</span>
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const d = new Date(due + 'T00:00:00')
  const diff = Math.round((d.getTime() - today.getTime()) / 86400000)
  const label = diff === 0 ? '오늘 마감' : diff > 0 ? `D-${diff}` : `${-diff}일 지남`
  const cls = done ? 'text-gray-400' : diff < 0 ? 'font-semibold text-red-600' : diff <= 3 ? 'font-semibold text-amber-600' : 'text-gray-500'
  return <span className={`whitespace-nowrap text-xs ${cls}`}>{`${d.getMonth() + 1}/${d.getDate()}`} · {label}</span>
}

export function StatusSelect({ value, onChange, disabled }: { value: TaskStatus; onChange: (s: TaskStatus) => void; disabled?: boolean }) {
  return (
    <select value={value} disabled={disabled} onChange={(e) => onChange(e.target.value as TaskStatus)} aria-label="진행 상태"
      className={`rounded border-0 py-0.5 pl-2 pr-7 text-xs font-medium focus:ring-1 focus:ring-indigo-500 disabled:opacity-70 ${TASK_STATUS[value][1]}`}>
      {(Object.keys(TASK_STATUS) as TaskStatus[]).map((s) => <option key={s} value={s}>{TASK_STATUS[s][0]}</option>)}
    </select>
  )
}
