"""인증/권한 의존성."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Meeting, Participant, User
from .security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다.")
    user_id = decode_access_token(cred.credentials)
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "인증 정보가 유효하지 않습니다. 다시 로그인해 주세요.")
    return user


def can_view(meeting: Meeting, user: User, db: Session) -> bool:
    if user.role == "admin" or meeting.owner_id == user.id:
        return True
    # 참석자로 초대된 사용자(같은 이메일로 가입)는 열람 가능
    return (
        db.scalar(
            select(Participant.id).where(
                Participant.meeting_id == meeting.id, Participant.email == user.email.lower()
            )
        )
        is not None
    )


def can_edit(meeting: Meeting, user: User) -> bool:
    return user.role == "admin" or meeting.owner_id == user.id


def get_meeting_for_view(meeting_id: int, db: Session, user: User) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    # 존재 여부를 노출하지 않도록 권한 없음도 404로 처리
    if meeting is None or not can_view(meeting, user, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "회의를 찾을 수 없습니다.")
    return meeting


def get_meeting_for_edit(meeting_id: int, db: Session, user: User) -> Meeting:
    meeting = get_meeting_for_view(meeting_id, db, user)
    if not can_edit(meeting, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "회의 생성자 또는 관리자만 수정할 수 있습니다.")
    return meeting
