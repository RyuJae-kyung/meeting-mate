"""이메일 발송 작업 처리.

중복 발송 방지:
- 모든 발송(즉시/예약)은 EmailJob 으로 만들고, 처리 직전에
  `UPDATE ... SET status='processing' WHERE id=? AND status='pending'` 로 원자적으로 선점한다.
  여러 워커/스케줄러가 동시에 실행돼도 한 작업은 한 번만 처리된다.
- 재시도 역시 `status='failed' → 'retrying'` 원자적 전환에 성공한 요청만 수행한다.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ...models import Briefing, EmailJob, EmailLog, Meeting, Participant
from .providers import EmailSendError, get_email_provider
from .templates import render_briefing_email

log = logging.getLogger(__name__)

STALE_PROCESSING_MINUTES = 15


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def render_for(db: Session, meeting: Meeting, p: Participant) -> tuple[str, str]:
    personal = db.scalar(select(Briefing).where(Briefing.participant_id == p.id))
    if personal is None:
        raise ValueError(f"{p.name}님의 개인 브리핑이 아직 생성되지 않았습니다.")
    general = db.scalar(select(Briefing).where(Briefing.meeting_id == meeting.id, Briefing.participant_id.is_(None)))
    return render_briefing_email(meeting, p, personal, general, list(meeting.glossary))


def _send_one(db: Session, meeting: Meeting, p: Participant, job_id: int | None) -> EmailLog:
    provider_name = "unknown"
    subject = f"[Meeting Mate] {meeting.title} 사전 브리핑"
    html = ""
    try:
        provider = get_email_provider()
        provider_name = provider.name
        subject, html = render_for(db, meeting, p)
        result = provider.send(p.email, subject, html)
        entry = EmailLog(meeting_id=meeting.id, participant_id=p.id, job_id=job_id, recipient=p.email, subject=subject,
                         body_html=html, status="sent", provider=provider_name, provider_message_id=result.message_id, sent_at=now_utc())
    except (EmailSendError, ValueError) as e:
        log.warning("이메일 발송 실패 to=%s: %s", p.email, e)
        entry = EmailLog(meeting_id=meeting.id, participant_id=p.id, job_id=job_id, recipient=p.email, subject=subject,
                         body_html=html, status="failed", provider=provider_name, error=str(e)[:2000])
    db.add(entry)
    return entry


def claim_job(db: Session, job_id: int) -> bool:
    res = db.execute(
        update(EmailJob).where(EmailJob.id == job_id, EmailJob.status == "pending").values(status="processing")
    )
    db.commit()
    return res.rowcount == 1


def process_job(db: Session, job_id: int) -> list[EmailLog]:
    """작업을 선점한 경우에만 발송한다. 선점에 실패하면 빈 목록."""
    if not claim_job(db, job_id):
        return []
    job = db.get(EmailJob, job_id)
    db.refresh(job)
    meeting = db.get(Meeting, job.meeting_id)
    logs: list[EmailLog] = []
    try:
        participants = {p.id: p for p in meeting.participants}
        for pid in job.participant_ids:
            p = participants.get(pid)
            if p is None:  # 예약 후 참석자가 삭제된 경우
                continue
            logs.append(_send_one(db, meeting, p, job.id))
        failed = sum(1 for l in logs if l.status == "failed")
        job.status = "done" if failed == 0 else ("failed" if failed == len(logs) else "partial")
        if not logs:
            job.status, job.error = "failed", "발송 대상 참석자가 없습니다."
    except Exception as e:  # 예기치 못한 오류: 작업을 실패로 기록
        log.exception("이메일 작업 처리 오류 job=%s", job_id)
        db.rollback()
        job = db.get(EmailJob, job_id)
        job.status, job.error = "failed", f"{type(e).__name__}: {e}"[:2000]
        logs = []
    job.processed_at = now_utc()
    db.commit()
    return logs


def retry_log(db: Session, log_id: int) -> EmailLog | None:
    """실패한 발송을 재시도. 동시에 두 번 눌러도 한 번만 수행된다."""
    res = db.execute(update(EmailLog).where(EmailLog.id == log_id, EmailLog.status == "failed").values(status="retrying"))
    db.commit()
    if res.rowcount != 1:
        return None
    entry = db.get(EmailLog, log_id)
    db.refresh(entry)
    meeting = db.get(Meeting, entry.meeting_id)
    if entry.email_type == "task_reminder":
        return _retry_task_reminder(db, entry, meeting)
    p = db.get(Participant, entry.participant_id) if entry.participant_id else None
    if p is None:
        entry.status, entry.error = "failed", "참석자가 삭제되어 재시도할 수 없습니다."
        db.commit()
        return entry
    entry.attempts += 1
    try:
        provider = get_email_provider()
        entry.provider = provider.name
        subject, html = render_for(db, meeting, p)
        result = provider.send(p.email, subject, html)
        entry.subject, entry.body_html, entry.recipient = subject, html, p.email
        entry.status, entry.error, entry.provider_message_id, entry.sent_at = "sent", None, result.message_id, now_utc()
    except (EmailSendError, ValueError) as e:
        entry.status, entry.error = "failed", str(e)[:2000]
    db.commit()
    return entry


def _retry_task_reminder(db: Session, entry: EmailLog, meeting: Meeting) -> EmailLog:
    from ...models import Task
    from ..task_reminders import today_local
    from .templates import render_task_reminder

    task = db.get(Task, entry.task_id) if entry.task_id else None
    if task is None or not task.assignee_email:
        entry.status, entry.error = "failed", "업무가 삭제되었거나 담당자 이메일이 없어 재시도할 수 없습니다."
        db.commit()
        return entry
    entry.attempts += 1
    try:
        provider = get_email_provider()
        entry.provider = provider.name
        subject, html = render_task_reminder(task, meeting, today_local())
        result = provider.send(task.assignee_email, subject, html)
        entry.subject, entry.body_html, entry.recipient = subject, html, task.assignee_email
        entry.status, entry.error, entry.provider_message_id, entry.sent_at = "sent", None, result.message_id, now_utc()
    except EmailSendError as e:
        entry.status, entry.error = "failed", str(e)[:2000]
    db.commit()
    return entry


def run_due_jobs(db: Session) -> int:
    """스케줄러에서 호출: 예정 시각이 지난 pending 작업 처리."""
    # 서버가 처리 중 비정상 종료되어 processing 에 멈춘 작업은 failed 로 정리 (자동 재발송하지 않음 → 중복 방지)
    db.execute(
        update(EmailJob)
        .where(EmailJob.status == "processing", EmailJob.created_at < now_utc() - timedelta(minutes=STALE_PROCESSING_MINUTES),
               EmailJob.processed_at.is_(None), EmailJob.scheduled_at < now_utc() - timedelta(minutes=STALE_PROCESSING_MINUTES))
        .values(status="failed", error="처리 중 서버가 중단되었습니다. 발송 내역을 확인 후 필요하면 재발송하세요.", processed_at=now_utc())
    )
    db.commit()
    due = db.scalars(
        select(EmailJob.id).where(EmailJob.status == "pending", EmailJob.scheduled_at <= now_utc()).order_by(EmailJob.scheduled_at).limit(50)
    ).all()
    count = 0
    for job_id in due:
        if process_job(db, job_id):
            count += 1
    return count
