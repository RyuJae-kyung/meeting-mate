import json
from types import SimpleNamespace

from app.services.ai import set_provider_override
from app.services.ai.openai_provider import OpenAIProvider

from .conftest import make_docx, make_pdf, register


def setup(client, auth, meeting):
    mid = meeting["id"]
    client.post(f"/api/meetings/{mid}/materials", headers=auth,
                files=[("files", ("plan.pdf", make_pdf(), "application/pdf")), ("files", ("req.docx", make_docx(), "application/octet-stream"))])
    client.post(f"/api/meetings/{mid}/briefings/generate", headers=auth)
    return mid


def test_grounded_answer_with_citations(client, auth, meeting):
    mid = setup(client, auth, meeting)
    r = client.post(f"/api/meetings/{mid}/questions", json={"question": "예산은 얼마로 산정되었나요?"}, headers=auth)
    assert r.status_code == 201, r.text
    q = r.json()
    assert q["grounded"] in ("materials", "partial") and q["source"] == "mock"
    assert q["citations"] and q["citations"][0]["file"] == "plan.pdf" and q["citations"][0]["loc"] == "p.2"
    assert "5천만원" in q["citations"][0]["quote"]


def test_not_found_is_marked(client, auth, meeting):
    mid = setup(client, auth, meeting)
    q = client.post(f"/api/meetings/{mid}/questions", json={"question": "점심 메뉴는 무엇인가요?"}, headers=auth).json()
    assert q["grounded"] == "none" and q["citations"] == [] and "찾을 수 없습니다" in q["answer"]


def test_glossary_term_separated_as_general_knowledge(client, auth, meeting):
    mid = setup(client, auth, meeting)
    q = client.post(f"/api/meetings/{mid}/questions", json={"question": "이 문서에서 말하는 API Gateway가 무엇인가요?"}, headers=auth).json()
    assert q["general_knowledge"] and "API Gateway" in q["general_knowledge"]
    assert q["citations"]  # 자료 속 사용 문맥도 함께


def test_meeting_info_is_a_source(client, auth, meeting):
    mid = setup(client, auth, meeting)
    q = client.post(f"/api/meetings/{mid}/questions", json={"question": "이번 회의에서 가장 중요한 안건은 무엇인가요?"}, headers=auth).json()
    assert q["grounded"] != "none" and any(c["file"] == "회의 정보" and c["loc"] == "안건" for c in q["citations"])


def test_history_is_per_user_and_participant_can_ask(client, auth, meeting):
    mid = setup(client, auth, meeting)
    client.post(f"/api/meetings/{mid}/questions", json={"question": "예산은?"}, headers=auth)
    dev = register(client, "dev@test.com", "김개발")
    r = client.post(f"/api/meetings/{mid}/questions", json={"question": "내가 개발 담당자인데 API 관련해 무엇을 준비해야 하나요?"}, headers=dev)
    assert r.status_code == 201
    assert len(client.get(f"/api/meetings/{mid}/questions", headers=dev).json()) == 1
    assert len(client.get(f"/api/meetings/{mid}/questions", headers=auth).json()) == 1
    stranger = register(client, "x@test.com", "외부인")
    assert client.post(f"/api/meetings/{mid}/questions", json={"question": "예산은?"}, headers=stranger).status_code == 404
    qid = r.json()["id"]
    assert client.delete(f"/api/questions/{qid}", headers=auth).status_code == 404  # 남의 질문
    assert client.delete(f"/api/questions/{qid}", headers=dev).status_code == 204


def test_openai_fabricated_citation_dropped(client, auth, meeting):
    mid = setup(client, auth, meeting)
    import re

    reply = {"answer": "예산은 5천만원입니다.", "grounded": "materials", "citations": [], "general_knowledge": None}
    p = OpenAIProvider.__new__(OpenAIProvider)
    p.model, p.max_chars = "m", 60000
    calls = []

    def create(**kw):
        calls.append(kw)
        if not reply.get("_fixed"):
            # 프롬프트에 제공된 조각 중 plan.pdf p.2 의 번호를 찾아 인용 + 존재하지 않는 S99 를 지어냄
            ref = re.search(r"\[(S\d+)\] \(plan\.pdf p\.2\)", kw["messages"][1]["content"]).group(1)
            reply["citations"] = [{"ref": ref, "quote": "예산은 5천만원"}, {"ref": "S99", "quote": "지어낸 출처"}]
        body = {k: v for k, v in reply.items() if k != "_fixed"}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(body)))])

    p.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    set_provider_override(p)
    q = client.post(f"/api/meetings/{mid}/questions", json={"question": "예산은 얼마인가요?"}, headers=auth).json()
    assert q["source"] == "openai" and len(q["citations"]) == 1 and q["citations"][0] == {"file": "plan.pdf", "loc": "p.2", "quote": "예산은 5천만원"}
    # 근거 없이 materials 라고 주장하면 none 으로 보정
    reply.update(citations=[], grounded="materials", _fixed=True)
    q = client.post(f"/api/meetings/{mid}/questions", json={"question": "예산은 얼마인가요?"}, headers=auth).json()
    assert q["grounded"] == "none"
