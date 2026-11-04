from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import EmailJob, EmailLog, Meeting, MeetingStatus, User
from ..schemas import DashboardOut, EmailJobOut, EmailLogOut, SystemStatusOut
from ..services.calendar import get_calendar_status
from ..services.email.dispatch import now_utc
from ..services.extraction import ALLOWED_TYPES
from .meetings import to_list_items, visible_meetings_query

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
    return DashboardOut(
        upcoming=to_list_items(db, list(upcoming)), recent=to_list_items(db, list(recent)), ready=to_list_items(db, list(ready)),
        recent_emails=[EmailLogOut.model_validate(e) for e in emails], pending_email_jobs=[EmailJobOut.model_validate(j) for j in pending],
        counts={"scheduled": by_status.get("scheduled", 0), "ready": by_status.get("ready", 0), "completed": by_status.get("completed", 0), "failed_emails": failed},
    )


@router.get("/system/status", response_model=SystemStatusOut)
def system_status(user: User = Depends(get_current_user)):
    s = get_settings()
    return SystemStatusOut(
        ai_provider=s.ai_mode, ai_model=s.OPENAI_MODEL if s.ai_mode == "openai" else "mock-rule-based",
        email_provider=s.email_mode, email_from=s.EMAIL_FROM, scheduler_enabled=s.SCHEDULER_ENABLED,
        scheduler_interval_seconds=s.SCHEDULER_INTERVAL_SECONDS, calendar=get_calendar_status(),
        max_upload_mb=s.MAX_UPLOAD_MB, allowed_file_types=list(ALLOWED_TYPES),
    )
