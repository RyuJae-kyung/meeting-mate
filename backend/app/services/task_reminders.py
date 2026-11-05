"""후속 업무 마감 임박 알림.

조건: 미완료 + 알림 켜짐 + 담당자 이메일 있음 + 오늘 <= 마감일 <= 오늘+N일 + 아직 알림 안 보냄
      + 담당자가 가입 사용자라면 설정에서 이메일 알림을 켠 경우.
중복 방지: reminder_sent_at IS NULL 조건으로 원자적으로 선점한 경우에만 발송.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import EmailLog, Meeting, Task, TaskStatus, User
from .email.providers import EmailSendError, get_email_provider
from .email.templates import render_task_reminder

log = logging.getLogger(__name__)


def today_local() -> date:
    return datetime.now(ZoneInfo(get_settings().DISPLAY_TIMEZONE)).date()


def _send(db: Session, task: Task, today: date) -> EmailLog:
    meeting = db.get(Meeting, task.meeting_id)
    subject, html, provider_name = f"[Meeting Mate] 후속 업무 알림 · {task.title}", "", "unknown"
    try:
        provider = get_email_provider()
        provider_name = provider.name
        subject, html = render_task_reminder(task, meeting, today)
        r = provider.send(task.assignee_email, subject, html)
        entry = EmailLog(meeting_id=meeting.id, participant_id=task.assignee_participant_id, task_id=task.id, recipient=task.assignee_email,
                         email_type="task_reminder", subject=subject, body_html=html, status="sent", provider=provider_name,
                         provider_message_id=r.message_id, sent_at=datetime.now(timezone.utc))
    except EmailSendError as e:
        log.warning("업무 알림 발송 실패 task=%s: %s", task.id, e)
        entry = EmailLog(meeting_id=meeting.id, participant_id=task.assignee_participant_id, task_id=task.id, recipient=task.assignee_email,
                         email_type="task_reminder", subject=subject, body_html=html, status="failed", provider=provider_name, error=str(e)[:2000])
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def claim(db: Session, task_id: int) -> bool:
    res = db.execute(update(Task).where(Task.id == task_id, Task.reminder_sent_at.is_(None)).values(reminder_sent_at=datetime.now(timezone.utc)))
    db.commit()
    return res.rowcount == 1


def send_now(db: Session, task: Task) -> EmailLog:
    """사용자가 직접 요청한 알림 (마감일 조건과 무관, 1회 발송 기록을 남김)."""
    db.execute(update(Task).where(Task.id == task.id).values(reminder_sent_at=datetime.now(timezone.utc)))
    db.commit()
    return _send(db, task, today_local())


def run_due_reminders(db: Session, today: date | None = None) -> int:
    today = today or today_local()
    days = get_settings().TASK_REMINDER_DAYS_BEFORE
    opted_out = exists().where(and_(User.email == Task.assignee_email, User.email_notifications.is_(False)))
    ids = db.scalars(
        select(Task.id).where(
            Task.status != TaskStatus.DONE, Task.reminder_enabled.is_(True), Task.reminder_sent_at.is_(None),
            Task.assignee_email.is_not(None), Task.due_date.is_not(None),
            Task.due_date >= today, Task.due_date <= today + timedelta(days=days), ~opted_out,
        ).limit(100)
    ).all()
    sent = 0
    for tid in ids:
        if claim(db, tid):
            _send(db, db.get(Task, tid), today)
            sent += 1
    return sent
