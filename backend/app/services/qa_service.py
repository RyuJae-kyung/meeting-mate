"""회의 자료 기반 질의응답."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Briefing, Meeting, Question, User
from .ai import MaterialCtx, get_ai_provider
from .briefing_service import build_ctx
from .retrieval import search

BRIEFING_SECTIONS = {
    "purpose_summary": "회의 목적 요약", "agenda_items": "주요 안건", "expected_discussions": "핵심 논의 예상",
    "pre_questions": "사전 질문", "checklist": "준비 체크리스트", "issues": "예상 쟁점",
}


def _extra_sources(db: Session, meeting: Meeting) -> list[MaterialCtx]:
    """업로드 자료 외에 회의 정보와 AI 브리핑도 출처로 검색한다 (출처명으로 구분)."""
    info = [{"loc": "목적", "text": f"회의 목적: {meeting.purpose}"}] if meeting.purpose else []
    if meeting.agenda_items:
        info.append({"loc": "안건", "text": "회의 안건:\n" + "\n".join(f"{i}. {a}" for i, a in enumerate(meeting.agenda_items, 1))})
    out = [MaterialCtx(filename="회의 정보", title=meeting.title, segments=info)] if info else []
    b = db.scalar(select(Briefing).where(Briefing.meeting_id == meeting.id, Briefing.participant_id.is_(None)))
    if b:
        segs = [{"loc": label, "text": "\n".join(f"{label}: {i['text']}" for i in b.content.get(key, []))}
                for key, label in BRIEFING_SECTIONS.items() if b.content.get(key)]
        out.append(MaterialCtx(filename="AI 사전 브리핑(추론 포함)", title=None, segments=segs))
    return out


def _briefing_summary(db: Session, meeting: Meeting) -> str:
    b = db.scalar(select(Briefing).where(Briefing.meeting_id == meeting.id, Briefing.participant_id.is_(None)))
    if not b:
        return ""
    c = b.content
    lines = [i["text"] for k in ("purpose_summary", "agenda_items", "issues") for i in c.get(k, [])]
    return "\n".join(f"- {t}" for t in lines)[:3000]


def ask(db: Session, meeting: Meeting, user: User, question: str) -> Question:
    provider = get_ai_provider()
    ctx = build_ctx(meeting)
    chunks = search(question, ctx.materials + _extra_sources(db, meeting), k=6)
    glossary = [{"term": g.term, "easy_explanation": g.easy_explanation} for g in meeting.glossary]
    res = provider.answer_question(ctx, question, chunks, glossary, _briefing_summary(db, meeting))
    by_ref = {c.ref: c for c in chunks}
    citations = []
    for c in res.get("citations", []):
        chunk = by_ref.get(str(c.get("ref")))
        if chunk is None:  # 제공하지 않은 출처를 AI가 지어낸 경우 제외
            continue
        quote = str(c.get("quote") or "")[:500]
        citations.append({"file": chunk.file, "loc": chunk.loc, "quote": quote or chunk.text[:200]})
    grounded = res["grounded"]
    if grounded == "materials" and citations and all(c["file"].startswith("AI 사전 브리핑") for c in citations):
        grounded = "partial"  # AI가 추론한 브리핑만 근거라면 '자료 근거'라고 표시하지 않음
    if grounded in ("materials", "partial") and not citations:
        # 근거 표시가 없으면 '자료 근거'라고 주장할 수 없음
        grounded = "none" if not res.get("general_knowledge") else "partial"
    q = Question(meeting_id=meeting.id, user_id=user.id, question=question, answer=res["answer"], grounded=grounded,
                 citations=citations, general_knowledge=res.get("general_knowledge"), source=provider.name)
    db.add(q)
    db.commit()
    db.refresh(q)
    return q
