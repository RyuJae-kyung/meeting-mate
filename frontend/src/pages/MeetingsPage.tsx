import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { MeetingListItem } from '../api/types'
import MeetingRow from '../components/MeetingRow'
import { Alert, EmptyState, PageLoader } from '../components/ui'

const FILTERS = [['', '전체'], ['scheduled', '예정'], ['ready', '준비 완료'], ['completed', '진행 완료']] as const

export default function MeetingsPage() {
  const [items, setItems] = useState<MeetingListItem[] | null>(null)
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    const t = setTimeout(() => {
      api.get<MeetingListItem[]>('/meetings', { params: { status: status || undefined, q: q || undefined } })
        .then((r) => setItems(r.data)).catch((e) => setErr(errorMessage(e)))
    }, 200)
    return () => clearTimeout(t)
  }, [status, q])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">회의 목록</h1>
        <Link to="/meetings/new" className="btn-primary">+ 새 회의</Link>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border border-gray-200 bg-white p-0.5">
          {FILTERS.map(([v, l]) => (
            <button key={v} onClick={() => setStatus(v)} className={`rounded px-3 py-1 text-sm ${status === v ? 'bg-gray-100 font-medium' : 'text-gray-500'}`}>{l}</button>
          ))}
        </div>
        <input className="input max-w-xs" placeholder="회의 제목 검색" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {err && <Alert>{err}</Alert>}
      {!items ? <PageLoader /> : items.length ? (
        <div className="card divide-y">{items.map((m) => <MeetingRow key={m.id} m={m} />)}</div>
      ) : <EmptyState title="조건에 맞는 회의가 없습니다" />}
    </div>
  )
}
