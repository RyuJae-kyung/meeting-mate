from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import can_edit, get_current_user, get_meeting_for_edit
from ..models import Meeting, Participant, Task, TaskStatus, User
from ..schemas import EmailLogOut, TaskCreateIn, TaskOut, TaskStatusIn, TaskUpdateIn
from ..services.result_service import apply_assignee, new_task
from ..services.task_reminders import send_now, today_local

router = APIRouter(prefix="/api", tags=["tasks"])


def visible_tasks_query(user: User):
    q = select(Task).join(Meeting, Meeting.id == Task.meeting_id)
    if user.role != "admin":
        email = user.email.lower()
        invited = exists().where(Participant.meeting_id == Meeting.id, Participant.email == email)
        q = q.where(or_(Meeting.owner_id == user.id, invited, Task.assignee_email == email))
    return q


def to_task_out(t: Task, user: User, db: Session) -> TaskOut:
    m = db.get(Meeting, t.meeting_id)
    editable = can_edit(m, user)
    return TaskOut.model_validate(t).model_copy(update={
        "meeting_title": m.title, "can_edit": editable,
        "can_update_status": editable or (t.assignee_email is not None and t.assignee_email == user.email.lower()),
    })


def _task(tid: int, db: Session, user: User) -> Task:
    t = db.scalar(visible_tasks_query(user).where(Task.id == tid))
    if t is None:
        raise HTTPException(404, "업무를 찾을 수 없습니다.")
    return t


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(scope: str = Query("all", pattern="^(all|mine)$"), status_: str | None = Query(None, alias="status"),
               meeting_id: int | None = None, assignee: str | None = None, due: str | None = Query(None, pattern="^(overdue|soon)$"),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = visible_tasks_query(user)
    if scope == "mine":
        q = q.where(Task.assignee_email == user.email.lower())
    if status_ == "open":
        q = q.where(Task.status != TaskStatus.DONE)
    elif status_:
        q = q.where(Task.status == status_)
    if meeting_id:
        q = q.where(Task.meeting_id == meeting_id)
    if assignee:
        q = q.where(Task.assignee_name == assignee)
    today = today_local()
    if due == "overdue":
        q = q.where(Task.due_date < today, Task.status != TaskStatus.DONE)
    elif due == "soon":
        q = q.where(Task.due_date >= today, Task.due_date <= today + timedelta(days=3), Task.status != TaskStatus.DONE)
    tasks = db.scalars(q.order_by(Task.status == TaskStatus.DONE, Task.due_date.asc().nulls_last(), Task.id)).all()
    return [to_task_out(t, user, db) for t in tasks]


@router.post("/meetings/{meeting_id}/tasks", response_model=TaskOut, status_code=201)
def create_task(meeting_id: int, body: TaskCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for_edit(meeting_id, db, user)
    t = new_task(m, user, body, from_ai=False)
    t.status = body.status
    if t.status == TaskStatus.DONE:
        t.completed_at = datetime.now(timezone.utc)
    db.add(t)
    db.commit()
    db.refresh(t)
    return to_task_out(t, user, db)


def _set_status(t: Task, new: str) -> None:
    if new == t.status:
        return
    t.status = new
    t.completed_at = datetime.now(timezone.utc) if new == TaskStatus.DONE else None


@router.put("/tasks/{tid}", response_model=TaskOut)
def update_task(tid: int, body: TaskUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = _task(tid, db, user)
    m = db.get(Meeting, t.meeting_id)
    if not can_edit(m, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "업무 내용은 회의 생성자 또는 관리자만 수정할 수 있습니다.")
    data = body.model_dump(exclude_unset=True)
    if "assignee_participant_id" in data or "assignee_name" in data:
        apply_assignee(m, t, data.get("assignee_participant_id"), data.get("assignee_name") or "")
    if "due_date" in data and data["due_date"] != t.due_date:
        t.due_date = data["due_date"]
        t.reminder_sent_at = None  # 마감일이 바뀌면 알림을 다시 보낼 수 있게
    for k in ("title", "description", "priority", "reminder_enabled"):
        if data.get(k) is not None:
            setattr(t, k, data[k])
    if data.get("status"):
        _set_status(t, data["status"])
    db.commit()
    db.refresh(t)
    return to_task_out(t, user, db)


@router.patch("/tasks/{tid}/status", response_model=TaskOut)
def update_status(tid: int, body: TaskStatusIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """진행 상태 변경: 회의 생성자/관리자 또는 담당자 본인."""
    t = _task(tid, db, user)
    out = to_task_out(t, user, db)
    if not out.can_update_status:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "담당자 본인 또는 회의 생성자만 상태를 바꿀 수 있습니다.")
    _set_status(t, body.status)
    db.commit()
    db.refresh(t)
    return to_task_out(t, user, db)


@router.delete("/tasks/{tid}", status_code=204)
def delete_task(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = _task(tid, db, user)
    if not can_edit(db.get(Meeting, t.meeting_id), user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "회의 생성자 또는 관리자만 삭제할 수 있습니다.")
    db.delete(t)
    db.commit()


@router.post("/tasks/{tid}/remind", response_model=EmailLogOut)
def remind(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """담당자에게 지금 알림 이메일 발송 (화면에서 확인 후 호출)."""
    t = _task(tid, db, user)
    if not can_edit(db.get(Meeting, t.meeting_id), user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "회의 생성자 또는 관리자만 알림을 보낼 수 있습니다.")
    if not t.assignee_email:
        raise HTTPException(status.HTTP_409_CONFLICT, "담당자가 참석자로 연결되어 있지 않아 이메일을 보낼 수 없습니다.")
    if t.status == TaskStatus.DONE:
        raise HTTPException(status.HTTP_409_CONFLICT, "완료된 업무입니다.")
    return send_now(db, t)
