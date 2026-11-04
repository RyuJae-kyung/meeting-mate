from app.services.ai import AIError, set_provider_override
from app.services.ai.mock_provider import MockProvider

from .conftest import make_docx, make_pdf, register


def setup_materials(client, auth, mid):
    r = client.post(f"/api/meetings/{mid}/materials", headers=auth,
                    files=[("files", ("plan.pdf", make_pdf(), "application/pdf")), ("files", ("req.docx", make_docx(), "application/octet-stream"))])
    assert r.status_code == 201


def test_generate_full_briefing(client, auth, meeting):
    mid = meeting["id"]
    setup_materials(client, auth, mid)
    r = client.post(f"/api/meetings/{mid}/briefings/generate", headers=auth)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["source"] == "mock" and res["participant_briefing_count"] == 3 and res["meeting_status"] == "ready"

    b = client.get(f"/api/meetings/{mid}/briefing", headers=auth).json()
    c = b["content"]
    assert set(c) == {"purpose_summary", "agenda_items", "expected_discussions", "pre_questions", "checklist", "issues", "material_summaries"}
    assert c["purpose_summary"][0]["basis"] == "fact"
    assert any(i["basis"] == "inference" for i in c["expected_discussions"])
    assert any(i["basis"] == "uncertain" for i in c["issues"])
    assert any("plan.pdf p." in (i["source"] or "") for i in c["material_summaries"])

    terms = {t["term"]: t for t in client.get(f"/api/meetings/{mid}/glossary", headers=auth).json()}
    assert {"MES", "ERP", "API Gateway", "KPI", "SCM", "SLA"} <= set(terms)
    assert terms["MES"]["source_ref"].startswith("plan.pdf p.")
    assert "MES" in terms["MES"]["context"]

    pbs = client.get(f"/api/meetings/{mid}/participant-briefings", headers=auth).json()
    assert len(pbs) == 3
    dev = next(x for x in pbs if x["participant"]["email"] == "dev@test.com")["briefing"]["content"]
    lead = next(x for x in pbs if x["participant"]["email"] == "lead@test.com")["briefing"]["content"]
    assert any("API" in i["text"] for i in dev["key_agenda"])
    assert any("예산" in i["text"] for i in lead["key_agenda"])
    assert dev["expected_questions"] != lead["expected_questions"]  # 역할별로 다른 브리핑
    assert dev["related_terms"]


def test_edit_briefing_and_glossary(client, auth, meeting):
    mid = meeting["id"]
    client.post(f"/api/meetings/{mid}/briefings/generate", headers=auth)
    b = client.get(f"/api/meetings/{mid}/briefing", headers=auth).json()
    content = b["content"]
    content["checklist"].append({"text": "노트북 지참", "basis": "fact", "source": "주최자 메모"})
    r = client.put(f"/api/briefings/{b['id']}", json={"content": content}, headers=auth)
    assert r.status_code == 200 and r.json()["is_edited"] and r.json()["content"]["checklist"][-1]["text"] == "노트북 지참"
    bad = dict(content, checklist=[{"text": "x", "basis": "made-up"}])
    assert client.put(f"/api/briefings/{b['id']}", json={"content": bad}, headers=auth).status_code == 422
    # 참석자 브리핑 수정
    pb = client.get(f"/api/meetings/{mid}/participant-briefings", headers=auth).json()[0]["briefing"]
    pc = dict(pb["content"], focus_summary="직접 수정한 요약")
    assert client.put(f"/api/briefings/{pb['id']}", json={"content": pc}, headers=auth).json()["content"]["focus_summary"] == "직접 수정한 요약"


def test_glossary_edit_without_materials(client, auth, meeting):
    mid = meeting["id"]
    setup_materials(client, auth, mid)
    client.post(f"/api/meetings/{mid}/briefings/generate", headers=auth)
    t = client.get(f"/api/meetings/{mid}/glossary", headers=auth).json()[0]
    r = client.put(f"/api/glossary/{t['id']}", json={"easy_explanation": "쉬운 설명 수정"}, headers=auth)
    assert r.json()["easy_explanation"] == "쉬운 설명 수정" and r.json()["is_edited"]
    assert client.delete(f"/api/glossary/{t['id']}", headers=auth).status_code == 204


def test_warnings_without_materials(client, auth, meeting):
    r = client.post(f"/api/meetings/{meeting['id']}/briefings/generate", headers=auth).json()
    assert any("자료가 없어" in w for w in r["warnings"])


def test_regenerate_personal_keeps_others(client, auth, meeting):
    mid = meeting["id"]
    client.post(f"/api/meetings/{mid}/briefings/generate", headers=auth)
    pid = meeting["participants"][0]["id"]
    r = client.post(f"/api/participants/{pid}/briefing/regenerate", headers=auth)
    assert r.status_code == 200 and r.json()["participant_id"] == pid


class FailingAI(MockProvider):
    name = "openai"

    def extract_glossary(self, ctx):
        raise AIError("simulated timeout")


def test_ai_failure_keeps_previous_results(client, auth, meeting):
    mid = meeting["id"]
    client.post(f"/api/meetings/{mid}/briefings/generate", headers=auth)
    before = client.get(f"/api/meetings/{mid}/briefing", headers=auth).json()
    set_provider_override(FailingAI())
    r = client.post(f"/api/meetings/{mid}/briefings/generate", headers=auth)
    assert r.status_code == 502 and "simulated timeout" in r.json()["detail"]
    after = client.get(f"/api/meetings/{mid}/briefing", headers=auth).json()
    assert after["id"] == before["id"] and after["source"] == "mock"


def test_participant_sees_only_own_briefing(client, auth, meeting):
    client.post(f"/api/meetings/{meeting['id']}/briefings/generate", headers=auth)
    h = register(client, "plan@test.com", "이기획")
    pbs = client.get(f"/api/meetings/{meeting['id']}/participant-briefings", headers=h).json()
    assert [x["participant"]["email"] for x in pbs] == ["plan@test.com"]


def test_public_briefing_link(client, auth, meeting):
    client.post(f"/api/meetings/{meeting['id']}/briefings/generate", headers=auth)
    token = meeting["participants"][0]["access_token"]
    r = client.get(f"/api/public/briefings/{token}")
    assert r.status_code == 200
    j = r.json()
    assert j["participant_name"] == "김개발" and j["personal"]["content"]["key_agenda"] and j["checklist"]
    assert client.get("/api/public/briefings/not-a-real-token-xxxxxxxx").status_code == 404
