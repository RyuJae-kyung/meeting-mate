import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { Dashboard } from '../api/types'
import MeetingRow from '../components/MeetingRow'
import { Alert, EmptyState, PageLoader } from '../components/ui'
import { DueLabel, PriorityBadge } from '../components/tasks'
import type { Task } from '../api/types'
import { fmtDateTime } from '../lib/format'
import { useAuth } from '../lib/auth'
import { EmailStatusBadge, JOB_MODE } from './meeting/EmailTab'

export default function DashboardPage() {
  const { user } = useAuth()
  const [d, setD] = useState<Dashboard | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.get<Dashboard>('/dashboard').then((r) => setD(r.data)).catch((e) => setErr(errorMessage(e))) }, [])

  if (err) return <Alert>{err}</Alert>
  if (!d) return <PageLoader />
  const stats = [
    { label: '예정된 회의', value: d.counts.scheduled },
    { label: '준비 완료', value: d.counts.ready },
    { label: '진행 완료', value: d.counts.completed },
    { label: '미완료 업무', value: d.counts.open_tasks, to: '/tasks' },
    { label: '기한 지난 업무', value: d.counts.overdue_tasks, warn: d.counts.overdue_tasks > 0, to: '/tasks?due=overdue' },
    { label: '발송 실패 이메일', value: d.counts.failed_emails, warn: d.counts.failed_emails > 0 },
  ]
  const taskList = (list: Task[], empty: string) => list.length ? (
    <div className="card divide-y">
      {list.map((t) => (
        <Link key={t.id} to={`/tasks?meeting=${t.meeting_id}`} className="flex items-center gap-2 px-4 py-2.5 hover:bg-gray-50">
          <PriorityBadge p={t.priority} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm">{t.title}</p>
            <p className="truncate text-xs text-gray-500">{t.assignee_name || '담당자 미지정'} · {t.meeting_title}</p>
          </div>
          <DueLabel due={t.due_date} />
        </Link>
      ))}
    </div>
  ) : <p className="text-sm text-gray-400">{empty}</p>
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">안녕하세요, {user?.name}님</h1>
          <p className="text-sm text-gray-500">다가오는 회의를 미리 준비하세요.</p>
        </div>
        <Link to="/meetings/new" className="btn-primary">+ 새 회의</Link>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {stats.map((s) => {
          const body = (<><p className="text-xs text-gray-500">{s.label}</p><p className={`mt-1 text-2xl font-semibold tabular-nums ${s.warn ? 'text-red-600' : ''}`}>{s.value}</p></>)
          return s.to ? <Link key={s.label} to={s.to} className="card px-4 py-3 hover:border-indigo-300">{body}</Link> : <div key={s.label} className="card px-4 py-3">{body}</div>
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <h2 className="mb-2 text-sm font-semibold">예정된 회의</h2>
          {d.upcoming.length ? (
            <div className="card divide-y">{d.upcoming.map((m) => <MeetingRow key={m.id} m={m} />)}</div>
          ) : (
            <EmptyState title="예정된 회의가 없습니다" desc="회의를 등록하고 자료를 올리면 AI 브리핑을 만들 수 있어요." action={<Link to="/meetings/new" className="btn-primary">회의 만들기</Link>} />
          )}
          <h2 className="mb-2 mt-6 text-sm font-semibold">준비 완료된 회의</h2>
          {d.ready.length ? <div className="card divide-y">{d.ready.map((m) => <MeetingRow key={m.id} m={m} />)}</div> : <p className="text-sm text-gray-400">브리핑이 생성된 예정 회의가 없습니다.</p>}
          <h2 className="mb-2 mt-6 text-sm font-semibold">최근 등록한 회의</h2>
          {d.recent.length ? <div className="card divide-y">{d.recent.map((m) => <MeetingRow key={m.id} m={m} />)}</div> : <p className="text-sm text-gray-400">아직 등록한 회의가 없습니다.</p>}
        </section>

        <section className="space-y-6">
          <div>
            <h2 className="mb-2 text-sm font-semibold">마감 임박 업무 <span className="font-normal text-gray-400">(3일 이내 · 기한 지남)</span></h2>
            {taskList(d.due_soon_tasks, '마감이 임박한 업무가 없습니다.')}
          </div>
          <div>
            <div className="mb-2 flex items-center justify-between"><h2 className="text-sm font-semibold">미완료 후속 업무</h2><Link to="/tasks" className="text-xs text-indigo-600">전체 보기</Link></div>
            {taskList(d.open_tasks, '미완료 업무가 없습니다.')}
          </div>
          <div>
            <h2 className="mb-2 text-sm font-semibold">예약된 발송</h2>
            <div className="card divide-y">
              {d.pending_email_jobs.length ? d.pending_email_jobs.map((j) => (
                <Link key={j.id} to={`/meetings/${j.meeting_id}?tab=email`} className="block px-4 py-2.5 text-sm hover:bg-gray-50">
                  <p className="font-medium">{fmtDateTime(j.scheduled_at)}</p>
                  <p className="text-xs text-gray-500">{JOB_MODE[j.mode]} · {j.participant_ids.length}명</p>
                </Link>
              )) : <p className="px-4 py-3 text-sm text-gray-400">예약된 발송이 없습니다.</p>}
            </div>
          </div>
          <div>
            <h2 className="mb-2 text-sm font-semibold">최근 이메일 발송 현황</h2>
            <div className="card divide-y">
              {d.recent_emails.length ? d.recent_emails.map((l) => (
                <Link key={l.id} to={`/meetings/${l.meeting_id}?tab=email`} className="block px-4 py-2.5 hover:bg-gray-50">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm">{l.recipient}</p>
                    <EmailStatusBadge status={l.status} provider={l.provider} />
                  </div>
                  <p className="truncate text-xs text-gray-500">{fmtDateTime(l.sent_at || l.created_at)}</p>
                </Link>
              )) : <p className="px-4 py-3 text-sm text-gray-400">발송 내역이 없습니다.</p>}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
