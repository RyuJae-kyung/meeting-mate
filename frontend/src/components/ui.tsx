import { useEffect, type ReactNode } from 'react'
import type { Basis, MeetingStatus } from '../api/types'

export function Spinner({ className = 'h-4 w-4' }: { className?: string }) {
  return <span className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${className}`} aria-label="로딩 중" />
}

export function PageLoader() {
  return <div className="flex justify-center py-20 text-gray-400"><Spinner className="h-6 w-6" /></div>
}

export function Alert({ kind = 'error', children, onClose }: { kind?: 'error' | 'success' | 'info' | 'warning'; children: ReactNode; onClose?: () => void }) {
  const styles = {
    error: 'border-red-200 bg-red-50 text-red-700',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    info: 'border-indigo-200 bg-indigo-50 text-indigo-700',
    warning: 'border-amber-200 bg-amber-50 text-amber-800',
  }[kind]
  return (
    <div className={`flex items-start justify-between gap-3 rounded-md border px-3 py-2 text-sm ${styles}`} role={kind === 'error' ? 'alert' : 'status'}>
      <div>{children}</div>
      {onClose && <button onClick={onClose} className="text-current opacity-60 hover:opacity-100" aria-label="닫기">×</button>}
    </div>
  )
}

const STATUS: Record<MeetingStatus, [string, string]> = {
  scheduled: ['예정', 'bg-gray-100 text-gray-700'],
  ready: ['준비 완료', 'bg-emerald-50 text-emerald-700'],
  completed: ['진행 완료', 'bg-slate-200 text-slate-600'],
}
export function StatusBadge({ status }: { status: MeetingStatus }) {
  const [label, cls] = STATUS[status]
  return <span className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>{label}</span>
}

const BASIS: Record<Basis, [string, string, string]> = {
  fact: ['자료 근거', 'bg-teal-50 text-teal-700', '회의 정보나 업로드 자료에 명시된 내용'],
  inference: ['AI 추론', 'bg-violet-50 text-violet-700', 'AI가 예상·추론한 내용 (결정 사항 아님)'],
  uncertain: ['확인 필요', 'bg-amber-50 text-amber-700', '근거가 부족하거나 불확실한 내용'],
}
export function BasisBadge({ basis }: { basis: Basis }) {
  const [label, cls, title] = BASIS[basis] ?? BASIS.inference
  return <span title={title} className={`inline-flex shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>{label}</span>
}

export function SourceBadge({ source }: { source: string | null | undefined }) {
  if (source === 'mock')
    return <span title="OPENAI_API_KEY 미설정 — 규칙 기반 Mock 결과입니다. 실제 AI 분석이 아닙니다." className="inline-flex rounded border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800">MOCK AI</span>
  if (source === 'openai') return <span className="inline-flex rounded border border-indigo-200 bg-indigo-50 px-1.5 py-0.5 text-[11px] font-semibold text-indigo-700">OpenAI</span>
  return null
}

export function EmptyState({ title, desc, action }: { title: string; desc?: string; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-gray-300 px-6 py-10 text-center">
      <p className="text-sm font-medium text-gray-700">{title}</p>
      {desc && <p className="mt-1 text-sm text-gray-500">{desc}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Modal({ open, title, onClose, children, footer, wide }: { open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onMouseDown={onClose}>
      <div className={`flex max-h-[90vh] w-full flex-col rounded-lg bg-white shadow-xl ${wide ? 'max-w-3xl' : 'max-w-lg'}`} onMouseDown={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="flex items-center justify-between border-b px-5 py-3">
          <h2 className="text-base font-semibold">{title}</h2>
          <button onClick={onClose} className="text-xl leading-none text-gray-400 hover:text-gray-600" aria-label="닫기">×</button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-sm font-semibold text-gray-900">{children}</h2>
      {right}
    </div>
  )
}

export function ItemList({ items, empty = '내용 없음' }: { items: { text: string; basis: Basis; source: string | null }[]; empty?: string }) {
  if (!items?.length) return <p className="text-sm text-gray-400">{empty}</p>
  return (
    <ul className="space-y-2">
      {items.map((it, i) => (
        <li key={i} className="flex items-start gap-2 text-sm leading-relaxed">
          <BasisBadge basis={it.basis} />
          <span className="text-gray-800">
            {it.text}
            {it.source && <span className="ml-1.5 text-xs text-gray-400">({it.source})</span>}
          </span>
        </li>
      ))}
    </ul>
  )
}
