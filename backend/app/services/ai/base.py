"""AI 공통 인터페이스와 입력 컨텍스트."""
from dataclasses import dataclass, field
from typing import Protocol


class AIError(Exception):
    """AI 호출/파싱 실패. 라우터에서 502로 변환한다."""


@dataclass
class MaterialCtx:
    filename: str
    title: str | None
    segments: list[dict]  # [{"loc": "p.1", "text": "..."}]
    keywords: list[str] = field(default_factory=list)


@dataclass
class ParticipantCtx:
    name: str
    role: str
    responsibility: str


@dataclass
class MeetingCtx:
    title: str
    purpose: str
    agenda_items: list[str]
    start_at_text: str
    location: str | None
    materials: list[MaterialCtx]
    participants: list[ParticipantCtx] = field(default_factory=list)

    def materials_as_text(self, max_chars: int) -> str:
        """[파일명 | 위치] 태그가 붙은 자료 본문. 출처 표시를 위해 위치 정보를 유지한다."""
        out: list[str] = []
        used = 0
        for m in self.materials:
            for seg in m.segments:
                chunk = f"[{m.filename} | {seg['loc']}]\n{seg['text']}\n"
                if used + len(chunk) > max_chars:
                    out.append("[... 분량 제한으로 이후 자료 일부 생략 ...]")
                    return "\n".join(out)
                out.append(chunk)
                used += len(chunk)
        return "\n".join(out) if out else "(업로드된 자료 없음)"


class AIProvider(Protocol):
    name: str  # "openai" | "mock"
    model: str | None

    def summarize_material(self, filename: str, title: str | None, segments: list[dict]) -> str: ...

    def generate_briefing(self, ctx: MeetingCtx) -> dict: ...

    def extract_glossary(self, ctx: MeetingCtx) -> list[dict]: ...

    def personal_briefing(self, ctx: MeetingCtx, participant: ParticipantCtx, glossary_terms: list[str]) -> dict: ...
