import { Link } from 'react-router-dom'
import type { MeetingListItem } from '../api/types'
import { fmtRange, relDays } from '../lib/format'
import { StatusBadge } from './ui'

export default function MeetingRow({ m }: { m: MeetingListItem }) {
  return (
    <Link to={`/meetings/${m.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-gray-50">
      <div className="w-14 shrink-0 text-center">
        <div className="text-xs font-semibold text-indigo-600">{relDays(m.start_at)}</div>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium">{m.title}</p>
          <StatusBadge status={m.status} />
        </div>
        <p className="mt-0.5 truncate text-xs text-gray-500">
          {fmtRange(m.start_at, m.end_at)}{m.location ? ` · ${m.location}` : ''} · 참석자 {m.participant_count}명 · 자료 {m.material_count}개
        </p>
      </div>
      {m.has_briefing && <span className="hidden shrink-0 text-xs text-emerald-600 sm:inline">브리핑 생성됨</span>}
    </Link>
  )
}
