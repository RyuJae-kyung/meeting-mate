from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_meeting_for_edit, get_meeting_for_view
from ..models import Briefing, EmailJob, EmailLog, User
from ..schemas import EmailJobOut, EmailLogDetail, EmailLogOut, EmailPreviewIn, EmailPreviewOut, EmailSendIn, EmailSendOut
from ..services.email.dispatch import now_utc, process_job, render_for, retry_log
from ..services.email.providers import EmailSendError, get_email_provider

router = APIRouter(prefix="/api", tags=["emails"])


@router.post("/meetings/{meeting_id}/emails/preview", response_model=EmailPreviewOut)
def preview(meeting_id: int, body: EmailPreviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for_edit(meeting_id, db, user)
    p = next((x for x in m.participants if x.id == body.participant_id), None)
    if p is None:
        raise HTTPException(404, "참석자를 찾을 수 없습니다.")
    try:
        subject, html = render_for(db, m, p)
        provider = get_email_provider().name
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except EmailSendError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    return EmailPreviewOut(to=p.email, subject=subject, html=html, provider=provider)


@router.post("/meetings/{meeting_id}/emails/send", response_model=EmailSendOut)
def send(meeting_id: int, body: EmailSendIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for_edit(meeting_id, db, user)
    if not body.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "발송 확인(confirm=true)이 필요합니다. 미리보기를 확인한 뒤 발송해 주세요.")
    pids = list(dict.fromkeys(body.participant_ids))
    valid = {p.id: p for p in m.participants}
    unknown = [pid for pid in pids if pid not in valid]
    if unknown:
        raise HTTPException(422, f"이 회의의 참석자가 아닙니다: {unknown}")
    have = set(db.scalars(select(Briefing.participant_id).where(Briefing.participant_id.in_(pids))).all())
    missing = [valid[pid].name for pid in pids if pid not in have]
    if missing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"개인 브리핑이 없는 참석자가 있습니다: {', '.join(missing)}. 먼저 브리핑을 생성해 주세요.")

    now = now_utc()
    if body.mode == "now":
        at = now
    elif body.mode == "scheduled":
        if body.scheduled_at is None or body.scheduled_at.tzinfo is None:
            raise HTTPException(422, "예약 발송에는 시간대가 포함된 scheduled_at 이 필요합니다.")
        at = body.scheduled_at
    else:
        if body.minutes_before is None:
            raise HTTPException(422, "회의 전 자동 발송에는 minutes_before 가 필요합니다.")
        at = m.start_at - timedelta(minutes=body.minutes_before)
    if body.mode != "now" and at <= now + timedelta(seconds=30):
        raise HTTPException(422, "발송 예정 시각이 이미 지났거나 너무 가깝습니다. 즉시 발송을 이용하거나 시간을 조정해 주세요.")

    job = EmailJob(meeting_id=m.id, created_by=user.id, participant_ids=pids, mode=body.mode,
                   minutes_before=body.minutes_before if body.mode == "before_meeting" else None, scheduled_at=at)
    db.add(job)
    db.commit()
    logs = process_job(db, job.id) if body.mode == "now" else []
    db.refresh(job)
    return EmailSendOut(job=EmailJobOut.model_validate(job), logs=[EmailLogOut.model_validate(l) for l in logs])


@router.get("/meetings/{meeting_id}/emails/logs", response_model=list[EmailLogOut])
def logs(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for_edit(meeting_id, db, user)
    return db.scalars(select(EmailLog).where(EmailLog.meeting_id == m.id).order_by(EmailLog.created_at.desc())).all()


@router.get("/meetings/{meeting_id}/emails/jobs", response_model=list[EmailJobOut])
def jobs(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for_edit(meeting_id, db, user)
    return db.scalars(select(EmailJob).where(EmailJob.meeting_id == m.id).order_by(EmailJob.created_at.desc())).all()


def _log_for_edit(lid: int, db: Session, user: User) -> EmailLog:
    l = db.get(EmailLog, lid)
    if l is None:
        raise HTTPException(404, "발송 기록을 찾을 수 없습니다.")
    get_meeting_for_edit(l.meeting_id, db, user)
    return l


@router.get("/emails/logs/{lid}", response_model=EmailLogDetail)
def log_detail(lid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _log_for_edit(lid, db, user)


@router.post("/emails/logs/{lid}/retry", response_model=EmailLogOut)
def retry(lid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _log_for_edit(lid, db, user)
    entry = retry_log(db, lid)
    if entry is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "실패한 발송만 재시도할 수 있습니다 (이미 재시도 중이거나 발송 완료).")
    return entry


@router.post("/emails/jobs/{jid}/cancel", response_model=EmailJobOut)
def cancel(jid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(EmailJob, jid)
    if job is None:
        raise HTTPException(404, "예약 작업을 찾을 수 없습니다.")
    get_meeting_for_edit(job.meeting_id, db, user)
    from sqlalchemy import update

    res = db.execute(update(EmailJob).where(EmailJob.id == jid, EmailJob.status == "pending").values(status="cancelled", processed_at=now_utc()))
    db.commit()
    if res.rowcount != 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "대기 중인 예약만 취소할 수 있습니다.")
    db.refresh(job)
    return job
