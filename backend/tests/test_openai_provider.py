"""실제 OpenAI 공급자의 프롬프트 구성·응답 파싱·검증 로직 테스트 (네트워크 호출 없이 가짜 클라이언트 사용)."""
import json
from types import SimpleNamespace

import pytest

from app.services.ai import AIError, set_provider_override
from app.services.ai.openai_provider import OpenAIProvider


class FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        content = self.replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def make_provider(replies):
    p = OpenAIProvider.__new__(OpenAIProvider)
    p.model, p.max_chars = "test-model", 60000
    p.client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(replies)))
    return p


ITEM = {"text": "MES 연동 범위 확정", "basis": "fact", "source": "plan.pdf p.1"}
GENERAL = {k: [ITEM] for k in ("purpose_summary", "agenda_items", "expected_discussions", "pre_questions", "checklist", "issues", "material_summaries")}
GLOSSARY = {"terms": [{"term": "MES", "easy_explanation": "생산관리 시스템", "work_meaning": "", "related_concepts": ["ERP"], "context": "MES에서", "source_ref": "plan.pdf p.1", "why_important": "", "is_uncertain": False}, {"bad": 1}]}
PERSONAL = {"focus_summary": "API 연동 준비", "key_agenda": [ITEM], "materials_to_review": [], "expected_questions": [], "preparation": [], "related_terms": ["MES", "없는용어"]}


def test_full_generation_with_openai_provider(client, auth, meeting):
    replies = [json.dumps(GENERAL), json.dumps(GLOSSARY)] + [json.dumps(PERSONAL)] * 3
    p = make_provider(replies)
    set_provider_override(p)
    r = client.post(f"/api/meetings/{meeting['id']}/briefings/generate", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "openai" and r.json()["glossary_count"] == 1  # 형식 오류 항목 제외
    calls = p.client.chat.completions.calls
    assert all(c["response_format"] == {"type": "json_object"} for c in calls)
    assert "basis=\"fact\"" in calls[0]["messages"][0]["content"]  # 사실/추론 구분 원칙 포함
    assert "김개발" in calls[2]["messages"][1]["content"]
    pb = client.get(f"/api/meetings/{meeting['id']}/participant-briefings", headers=auth).json()[0]["briefing"]
    assert pb["source"] == "openai" and pb["model"] == "test-model"
    assert pb["content"]["related_terms"] == ["MES"]  # 목록에 없는 용어 제거


def test_invalid_json_and_schema(client, auth, meeting):
    set_provider_override(make_provider(["not json"]))
    r = client.post(f"/api/meetings/{meeting['id']}/briefings/generate", headers=auth)
    assert r.status_code == 502 and "JSON" in r.json()["detail"]
    set_provider_override(make_provider([json.dumps({"purpose_summary": [{"text": "x", "basis": "decided"}]})]))
    assert client.post(f"/api/meetings/{meeting['id']}/briefings/generate", headers=auth).status_code == 502


def test_api_exception_wrapped():
    p = make_provider([])

    def boom(**kw):
        raise TimeoutError("read timeout")

    p.client.chat.completions.create = boom
    with pytest.raises(AIError, match="read timeout"):
        p.summarize_material("a.txt", None, [{"loc": "문단 1", "text": "hello"}])
