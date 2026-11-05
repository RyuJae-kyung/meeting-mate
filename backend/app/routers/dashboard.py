from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from datetime import timedelta

from ..models import EmailJob, EmailLog, Meeting, MeetingStatus, Task, TaskStatus, User
from ..schemas import DashboardOut, EmailJobOut, EmailLogOut, SystemStatusOut
from ..services.calendar import get_calendar_status
from ..services.email.dispatch import now_utc
from ..services.extraction import ALLOWED_TYPES
from ..services.task_reminders import today_local
from .meetings import to_list_items, visible_meetings_query
from .tasks import to_task_out, visible_tasks_query

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = now_utc()
    base = visible_meetings_query(user)
    upcoming = db.scalars(base.where(Meeting.start_at >= now, Meeting.status != MeetingStatus.COMPLETED).order_by(Meeting.start_at).limit(8)).all()
    recent = db.scalars(base.order_by(Meeting.created_at.desc()).limit(6)).all()
    ready = db.scalars(base.where(Meeting.status == MeetingStatus.READY, Meeting.start_at >= now).order_by(Meeting.start_at).limit(6)).all()
    own_ids = select(Meeting.id) if user.role == "admin" else select(Meeting.id).where(Meeting.owner_id == user.id)
    emails = db.scalars(select(EmailLog).where(EmailLog.meeting_id.in_(own_ids)).order_by(EmailLog.created_at.desc()).limit(8)).all()
    pending = db.scalars(select(EmailJob).where(EmailJob.meeting_id.in_(own_ids), EmailJob.status == "pending").order_by(EmailJob.scheduled_at).limit(8)).all()
    sub = base.subquery()
    by_status = dict(db.execute(select(sub.c.status, func.count()).group_by(sub.c.status)).all())
    failed = db.scalar(select(func.count()).select_from(EmailLog).where(EmailLog.meeting_id.in_(own_ids), EmailLog.status == "failed")) or 0
    # 업무: 내가 담당이거나 내가 만든 회의(관리자는 전체)에서 나온 미완료 업무
    tq = visible_tasks_query(user).where(Task.status != TaskStatus.DONE)
    if user.role != "admin":
        tq = tq.where((Task.assignee_email == user.email.lower()) | (Meeting.owner_id == user.id))
    today = today_local()
    open_all = db.scalars(tq.order_by(Task.due_date.asc().nulls_last(), Task.id)).all()
    due_soon = [t for t in open_all if t.due_date and t.due_date <= today + timedelta(days=3)]
    overdue = sum(1 for t in open_all if t.due_date and t.due_date < today)
    return DashboardOut(
        open_tasks=[to_task_out(t, user, db) for t in open_all[:8]],
        due_soon_tasks=[to_task_out(t, user, db) for t in due_soon[:8]],
        upcoming=to_list_items(db, list(upcoming)), recent=to_list_items(db, list(recent)), ready=to_list_items(db, list(ready)),
        recent_emails=[EmailLogOut.model_validate(e) for e in emails], pending_email_jobs=[EmailJobOut.model_validate(j) for j in pending],
        counts={"scheduled": by_status.get("scheduled", 0), "ready": by_status.get("ready", 0), "completed": by_status.get("completed", 0), "failed_emails": failed,
                "open_tasks": len(open_all), "overdue_tasks": overdue},
    )


@router.get("/system/status", response_model=SystemStatusOut)
def system_status(user: User = Depends(get_current_user)):
    s = get_settings()
    return SystemStatusOut(
        ai_provider=s.ai_mode, ai_model=s.OPENAI_MODEL if s.ai_mode == "openai" else "mock-rule-based",
        email_provider=s.email_mode, email_from=s.EMAIL_FROM, scheduler_enabled=s.SCHEDULER_ENABLED,
        scheduler_interval_seconds=s.SCHEDULER_INTERVAL_SECONDS, calendar=get_calendar_status(),
        task_reminder_days_before=s.TASK_REMINDER_DAYS_BEFORE,
        max_upload_mb=s.MAX_UPLOAD_MB, allowed_file_types=list(ALLOWED_TYPES),
    )
