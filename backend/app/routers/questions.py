from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_meeting_for_view
from ..models import Question, User
from ..schemas import QuestionIn, QuestionOut
from ..services.ai import AIError
from ..services.qa_service import ask

router = APIRouter(prefix="/api", tags=["questions"])


@router.post("/meetings/{meeting_id}/questions", response_model=QuestionOut, status_code=201)
def create_question(meeting_id: int, body: QuestionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """회의 자료·브리핑을 근거로 답변. 회의를 열람할 수 있는 사용자(참석자 포함) 누구나 질문 가능."""
    m = get_meeting_for_view(meeting_id, db, user)
    try:
        return ask(db, m, user, body.question.strip())
    except AIError as e:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 답변 생성에 실패했습니다. 잠시 후 다시 시도해 주세요. ({e})")


@router.get("/meetings/{meeting_id}/questions", response_model=list[QuestionOut])
def list_questions(meeting_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """본인이 한 질문 기록 (오래된 순)."""
    m = get_meeting_for_view(meeting_id, db, user)
    return db.scalars(select(Question).where(Question.meeting_id == m.id, Question.user_id == user.id).order_by(Question.created_at)).all()


@router.delete("/questions/{qid}", status_code=204)
def delete_question(qid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if q is None or q.user_id != user.id:
        raise HTTPException(404, "질문을 찾을 수 없습니다.")
    db.delete(q)
    db.commit()
