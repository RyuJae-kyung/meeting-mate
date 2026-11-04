"""OpenAI 기반 실제 AI 공급자. 모든 호출은 백엔드에서만 이루어진다."""
import json
import logging

from pydantic import ValidationError

from ...config import get_settings
from ...schemas import GeneralBriefingContent, GlossaryItemContent, PersonalBriefingContent
from .base import AIError, MeetingCtx, ParticipantCtx

log = logging.getLogger(__name__)

GROUNDING_RULES = """
[작성 원칙 — 반드시 지킬 것]
1. 회의 정보나 자료에 명시된 내용만 basis="fact" 로 표시하고, source 에 근거 위치를 "파일명 위치" 형식(예: "계획서.pdf p.3") 또는 "회의 정보"로 적는다.
2. 자료를 바탕으로 예상·추론한 내용은 basis="inference", 근거가 부족하거나 확인이 필요한 내용은 basis="uncertain" 으로 표시한다.
3. 자료에 없는 수치, 일정, 이름, 결정 사항을 만들어내지 않는다.
4. 아직 회의 전이므로, 어떤 내용도 회의에서 '결정되었다'고 표현하지 않는다.
5. 모든 문장은 자연스러운 한국어로 간결하게 작성한다.
6. 응답은 지정된 JSON 형식만 출력한다.
""".strip()

ITEM_SHAPE = '{"text": string, "basis": "fact"|"inference"|"uncertain", "source": string|null}'


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        from openai import OpenAI

        s = get_settings()
        if not s.OPENAI_API_KEY:
            raise AIError("OPENAI_API_KEY 가 설정되지 않았습니다.")
        self.model = s.OPENAI_MODEL
        self.max_chars = s.AI_MAX_CONTEXT_CHARS
        self.client = OpenAI(api_key=s.OPENAI_API_KEY, timeout=s.OPENAI_TIMEOUT_SECONDS, max_retries=2)

    # ---- 내부 ----
    def _chat_json(self, system: str, user: str) -> dict:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.2,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
        except Exception as e:  # openai.APIError, 네트워크 오류 등
            log.exception("OpenAI 호출 실패")
            raise AIError(f"AI 호출에 실패했습니다: {type(e).__name__}: {e}") from e
        raw = resp.choices[0].message.content or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise AIError("AI 응답을 JSON으로 해석할 수 없습니다.") from e
        if not isinstance(data, dict):
            raise AIError("AI 응답 형식이 올바르지 않습니다.")
        return data

    def _meeting_header(self, ctx: MeetingCtx) -> str:
        agenda = "\n".join(f"- {a}" for a in ctx.agenda_items) or "(안건 미입력)"
        people = "\n".join(f"- {p.name}: {p.role} / {p.responsibility}" for p in ctx.participants) or "(미입력)"
        return (
            f"[회의 정보]\n제목: {ctx.title}\n목적: {ctx.purpose or '(미입력)'}\n일시: {ctx.start_at_text}\n"
            f"장소: {ctx.location or '(미입력)'}\n안건:\n{agenda}\n참석자:\n{people}\n"
        )

    # ---- 공개 메서드 ----
    def summarize_material(self, filename: str, title: str | None, segments: list[dict]) -> str:
        body = "\n".join(f"[{s['loc']}] {s['text']}" for s in segments)[: self.max_chars]
        data = self._chat_json(
            "너는 업무 문서를 요약하는 조수다. 문서에 있는 내용만 사용하고 추측하지 않는다. "
            '{"summary": string} 형식 JSON으로 답한다.',
            f"파일명: {filename}\n제목: {title or '(없음)'}\n\n아래 문서의 주요 내용을 3~5문장으로 요약해라.\n\n{body}",
        )
        summary = str(data.get("summary", "")).strip()
        if not summary:
            raise AIError("AI 요약 결과가 비어 있습니다.")
        return summary

    def generate_briefing(self, ctx: MeetingCtx) -> dict:
        schema = (
            "{\n"
            f'  "purpose_summary": [{ITEM_SHAPE}],      // 회의 목적 요약 (1~3개)\n'
            f'  "agenda_items": [{ITEM_SHAPE}],         // 주요 안건 정리 (안건별 1개)\n'
            f'  "expected_discussions": [{ITEM_SHAPE}], // 핵심 논의 예상 사항\n'
            f'  "pre_questions": [{ITEM_SHAPE}],        // 사전에 확인해야 할 질문\n'
            f'  "checklist": [{ITEM_SHAPE}],            // 회의 전 준비 체크리스트\n'
            f'  "issues": [{ITEM_SHAPE}],               // 예상 쟁점 및 고려 사항\n'
            f'  "material_summaries": [{ITEM_SHAPE}]    // 관련 자료 핵심 요약 (파일별)\n'
            "}"
        )
        data = self._chat_json(
            "너는 직장인의 회의 사전 준비를 돕는 Meeting Mate 브리핑 작성자다.\n" + GROUNDING_RULES,
            f"{self._meeting_header(ctx)}\n[회의 자료]\n{ctx.materials_as_text(self.max_chars)}\n\n"
            f"위 내용을 바탕으로 참석자 공통 사전 브리핑을 작성해라. 형식:\n{schema}",
        )
        try:
            return GeneralBriefingContent.model_validate(data).model_dump()
        except ValidationError as e:
            raise AIError(f"AI 브리핑 형식 검증 실패: {e.errors()[:3]}") from e

    def extract_glossary(self, ctx: MeetingCtx) -> list[dict]:
        schema = (
            '{"terms": [{"term": string, "easy_explanation": string, "work_meaning": string, '
            '"related_concepts": [string], "context": string, "source_ref": string|null, '
            '"why_important": string, "is_uncertain": boolean}]}'
        )
        data = self._chat_json(
            "너는 회의 자료 속 전문 용어를 일반 사무직 참석자에게 쉽게 설명하는 조수다.\n"
            "- 일반 참석자가 이해하기 어려운 전문 용어, 약어, 기술 용어를 최대 15개 고른다.\n"
            "- 사전식 정의가 아니라 이 회의의 맥락에 맞춰 설명한다.\n"
            "- context 에는 자료에서 해당 용어가 쓰인 문장을 그대로 인용하고, source_ref 에 '파일명 위치'를 적는다.\n"
            "- 자료만으로 의미를 확정하기 어렵다면 is_uncertain=true 로 표시한다.\n" + GROUNDING_RULES,
            f"{self._meeting_header(ctx)}\n[회의 자료]\n{ctx.materials_as_text(self.max_chars)}\n\n형식:\n{schema}",
        )
        terms = data.get("terms", [])
        if not isinstance(terms, list):
            raise AIError("AI 용어 추출 결과 형식이 올바르지 않습니다.")
        out = []
        for t in terms:
            try:
                out.append(GlossaryItemContent.model_validate(t).model_dump())
            except ValidationError:
                log.warning("용어 항목 형식 오류로 제외: %s", t)
        return out

    def personal_briefing(self, ctx: MeetingCtx, participant: ParticipantCtx, glossary_terms: list[str]) -> dict:
        schema = (
            "{\n"
            '  "focus_summary": string,                // 이 참석자가 이번 회의에서 주목할 점 2~3문장\n'
            f'  "key_agenda": [{ITEM_SHAPE}],          // 본인에게 중요한 안건과 이유\n'
            f'  "materials_to_review": [{ITEM_SHAPE}], // 사전에 확인할 자료 (source에 위치)\n'
            f'  "expected_questions": [{ITEM_SHAPE}],  // 본인이 받을 수 있는 예상 질문\n'
            f'  "preparation": [{ITEM_SHAPE}],         // 본인이 준비해야 할 내용\n'
            '  "related_terms": [string]               // 아래 용어 목록 중 본인 업무와 관련된 용어\n'
            "}"
        )
        data = self._chat_json(
            "너는 참석자의 역할과 담당 업무에 맞춘 개인 회의 브리핑을 작성한다.\n"
            "역할별 관점 예시: 개발 담당자=기술 구현·시스템 연동·개발 이슈, 기획 담당자=사업 목적·일정·요구사항·의사결정, "
            "관리자=비용·일정·리스크·주요 결정, 영업 담당자=고객 요구·계약 조건·사업 진행 상황.\n" + GROUNDING_RULES,
            f"{self._meeting_header(ctx)}\n[대상 참석자]\n이름: {participant.name}\n역할: {participant.role or '(미입력)'}\n"
            f"담당 업무: {participant.responsibility or '(미입력)'}\n\n[이 회의의 전문 용어 목록]\n{', '.join(glossary_terms) or '(없음)'}\n\n"
            f"[회의 자료]\n{ctx.materials_as_text(self.max_chars)}\n\n형식:\n{schema}",
        )
        try:
            content = PersonalBriefingContent.model_validate(data).model_dump()
        except ValidationError as e:
            raise AIError(f"AI 개인 브리핑 형식 검증 실패: {e.errors()[:3]}") from e
        allowed = {t.lower() for t in glossary_terms}
        content["related_terms"] = [t for t in content["related_terms"] if t.lower() in allowed]
        return content
