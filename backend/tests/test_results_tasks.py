from datetime import date, datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Task
from app.services.email.providers import EmailSendError, SendResult, set_email_override
from app.services.task_reminders import run_due_reminders, today_local

from .conftest import register

RAW = """1차 연동 범위는 생산 실적과 자재 투입으로 확정했다.
2차 IoT 센서 연동 여부는 보류하고 다음 회의에서 다시 논의하기로 했다.
- 김개발: API 연동 테스트 11월 20일까지 (긴급)
이기획님이 다음 주 수요일까지 요구사항 문서를 정리해서 공유한다.
박팀장이 예산 승인을 월말까지 진행한다.
외부업체 최대리가 견적서를 금요일까지 보내기로 함.
SI 인력 투입 시점은 미정."""


def analyze(client, auth, mid, text=RAW, file=None):
    files = {"file": file} if file else None
    return client.post(f"/api/meetings/{mid}/result/analyze", data={"text": text}, files=files, headers=auth)


def test_analyze_creates_draft_only(client, auth, meeting):
    mid = meeting["id"]
    r = analyze(client, auth, mid)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["status"] == "draft" and res["source"] == "mock"
    assert res["decisions"] == ["1차 연동 범위는 생산 실적과 자재 투입으로 확정했다."]
    assert "SI 인력 투입 시점은 미정." in res["undecided"]
    assert res["further_discussion"]
    tasks = {t["assignee_name"]: t for t in res["draft_tasks"]}
    pids = {p["name"]: p["id"] for p in meeting["participants"]}
    assert tasks["김개발"]["due_date"] == "2030-11-20" and tasks["김개발"]["priority"] == "high"
    assert tasks["김개발"]["assignee_participant_id"] == pids["김개발"]
    assert tasks["이기획"]["due_date"] == "2030-11-13"  # 회의일 2030-11-10(일) 기준, 월요일 시작 주의 다음 주 수요일
    assert tasks["박팀장"]["due_date"] == "2030-11-30"
    assert tasks["최대리"]["assignee_participant_id"] is None and tasks["최대리"]["uncertain"] is True
    assert len(res["draft_tasks"]) == 4
    # 아직 업무는 생성되지 않음
    assert client.get("/api/tasks", headers=auth).json() == []


def test_analyze_validation_and_file(client, auth, meeting):
    mid = meeting["id"]
    assert analyze(client, auth, mid, text="짧음").status_code == 422
    assert analyze(client, auth, mid, text="", file=("a.exe", b"MZ", "application/octet-stream")).status_code == 415
    r = analyze(client, auth, mid, text="", file=("minutes.txt", "김개발님이 내일까지 배포 계획을 작성한다.".encode(), "text/plain"))
    assert r.status_code == 200 and r.json()["source_filename"] == "minutes.txt"
    assert r.json()["draft_tasks"][0]["due_date"] == "2030-11-11"


def test_confirm_creates_tasks_and_completes_meeting(client, auth, meeting):
    mid = meeting["id"]
    draft = analyze(client, auth, mid).json()
    pids = {p["name"]: p["id"] for p in meeting["participants"]}
    tasks = [
        {"title": "API 연동 테스트", "assignee_participant_id": pids["김개발"], "due_date": "2030-11-20", "priority": "high"},
        {"title": "견적서 수령", "assignee_name": "최대리", "due_date": None, "priority": "low", "reminder_enabled": False},
    ]
    body = {"summary": "수정한 요약", "decisions": draft["decisions"] + [" "], "undecided": draft["undecided"], "further_discussion": [], "tasks": tasks}
    r = client.post(f"/api/meetings/{mid}/result/confirm", json=body, headers=auth)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["meeting_status"] == "completed" and j["result"]["status"] == "confirmed" and j["result"]["summary"] == "수정한 요약"
    assert j["result"]["decisions"] == draft["decisions"]  # 공백 항목 제거
    t1, t2 = j["tasks"]
    assert t1["assignee_email"] == "dev@test.com" and t1["status"] == "todo" and t1["meeting_title"]
    assert t2["assignee_email"] is None and t2["assignee_name"] == "최대리"
    bad = dict(body, tasks=[{"title": "x", "assignee_participant_id": 99999}])
    assert client.post(f"/api/meetings/{mid}/result/confirm", json=bad, headers=auth).status_code == 422
    assert client.get(f"/api/meetings/{mid}/result", headers=auth).json()["status"] == "confirmed"


def make_tasks(client, auth, meeting):
    mid = meeting["id"]
    pids = {p["name"]: p["id"] for p in meeting["participants"]}
    today = today_local()
    body = {"tasks": [
        {"title": "내일 마감", "assignee_participant_id": pids["김개발"], "due_date": (today + timedelta(days=1)).isoformat()},
        {"title": "다음 주 마감", "assignee_participant_id": pids["김개발"], "due_date": (today + timedelta(days=7)).isoformat()},
        {"title": "기한 지남", "assignee_participant_id": pids["이기획"], "due_date": (today - timedelta(days=2)).isoformat()},
        {"title": "알림 꺼짐", "assignee_participant_id": pids["박팀장"], "due_date": today.isoformat(), "reminder_enabled": False},
        {"title": "마감 없음", "assignee_participant_id": pids["박팀장"]},
    ], "mark_completed": False}
    return {t["title"]: t for t in client.post(f"/api/meetings/{mid}/result/confirm", json=body, headers=auth).json()["tasks"]}


def test_task_list_filters_and_permissions(client, auth, meeting):
    tasks = make_tasks(client, auth, meeting)
    assert len(client.get("/api/tasks", headers=auth).json()) == 5
    assert [t["title"] for t in client.get("/api/tasks?due=overdue", headers=auth).json()] == ["기한 지남"]
    assert {t["title"] for t in client.get("/api/tasks?due=soon", headers=auth).json()} == {"내일 마감", "알림 꺼짐"}
    assert len(client.get("/api/tasks?assignee=박팀장", headers=auth).json()) == 2

    dev = register(client, "dev@test.com", "김개발")
    mine = client.get("/api/tasks?scope=mine", headers=dev).json()
    assert {t["title"] for t in mine} == {"내일 마감", "다음 주 마감"} and all(t["can_update_status"] and not t["can_edit"] for t in mine)
    tid = tasks["내일 마감"]["id"]
    r = client.patch(f"/api/tasks/{tid}/status", json={"status": "done"}, headers=dev)
    assert r.json()["status"] == "done" and r.json()["completed_at"]
    assert client.put(f"/api/tasks/{tid}", json={"title": "해킹"}, headers=dev).status_code == 403
    other = tasks["기한 지남"]["id"]  # 이기획 담당
    assert client.patch(f"/api/tasks/{other}/status", json={"status": "done"}, headers=dev).status_code == 403
    assert client.delete(f"/api/tasks/{other}", headers=dev).status_code == 403
    stranger = register(client, "x@test.com", "외부인")
    assert client.get("/api/tasks", headers=stranger).json() == []
    assert client.patch(f"/api/tasks/{other}/status", json={"status": "done"}, headers=stranger).status_code == 404
    # 생성자: 수정·재오픈·삭제
    r = client.put(f"/api/tasks/{tid}", json={"status": "in_progress", "priority": "high", "title": "수정됨"}, headers=auth).json()
    assert r["status"] == "in_progress" and r["completed_at"] is None and r["title"] == "수정됨"
    r = client.put(f"/api/tasks/{tid}", json={"assignee_participant_id": None, "assignee_name": "외부 담당"}, headers=auth).json()
    assert r["assignee_email"] is None and r["assignee_name"] == "외부 담당"
    assert client.delete(f"/api/tasks/{other}", headers=auth).status_code == 204
    # 수동 추가
    r = client.post(f"/api/meetings/{meeting['id']}/tasks", json={"title": "수동 업무", "assignee_name": "이기획", "priority": "low"}, headers=auth)
    assert r.status_code == 201 and r.json()["assignee_email"] == "plan@test.com" and r.json()["from_ai"] is False


def test_reminders_once_and_respect_settings(client, auth, meeting):
    tasks = make_tasks(client, auth, meeting)
    with SessionLocal() as db:
        assert run_due_reminders(db) == 1  # '내일 마감'만 (기한 지남·알림 꺼짐·마감 없음·다음 주 제외)
        assert run_due_reminders(db) == 0  # 중복 발송 없음
    logs = client.get(f"/api/meetings/{meeting['id']}/emails/logs", headers=auth).json()
    assert len(logs) == 1 and logs[0]["email_type"] == "task_reminder" and logs[0]["task_id"] == tasks["내일 마감"]["id"]
    assert logs[0]["recipient"] == "dev@test.com" and "내일 마감" in logs[0]["subject"]
    # 마감일 변경 시 다시 알림 가능 + 사용자가 알림을 끄면 발송 안 함
    tid = tasks["다음 주 마감"]["id"]
    client.put(f"/api/tasks/{tid}", json={"due_date": today_local().isoformat()}, headers=auth)
    dev = register(client, "dev@test.com", "김개발")
    client.put("/api/auth/me", json={"email_notifications": False}, headers=dev)
    with SessionLocal() as db:
        assert run_due_reminders(db) == 0
    client.put("/api/auth/me", json={"email_notifications": True}, headers=dev)
    with SessionLocal() as db:
        assert run_due_reminders(db) == 1


class FailOnce:
    name = "resend"

    def __init__(self):
        self.fail = True

    def send(self, to, subject, html):
        if self.fail:
            raise EmailSendError("simulated 500")
        return SendResult(message_id="re_ok")


def test_manual_remind_failure_and_retry(client, auth, meeting):
    tasks = make_tasks(client, auth, meeting)
    fp = FailOnce()
    set_email_override(fp)
    tid = tasks["다음 주 마감"]["id"]
    r = client.post(f"/api/tasks/{tid}/remind", headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "failed"
    fp.fail = False
    r2 = client.post(f"/api/emails/logs/{r.json()['id']}/retry", headers=auth)
    assert r2.json()["status"] == "sent" and r2.json()["attempts"] == 2
    with SessionLocal() as db:
        assert db.get(Task, tid).reminder_sent_at is not None
    # 담당자 이메일 없는 업무 / 권한 없음
    r = client.post(f"/api/meetings/{meeting['id']}/tasks", json={"title": "외부", "assignee_name": "외부인"}, headers=auth).json()
    assert client.post(f"/api/tasks/{r['id']}/remind", headers=auth).status_code == 409
    dev = register(client, "dev@test.com", "김개발")
    assert client.post(f"/api/tasks/{tid}/remind", headers=dev).status_code == 403


def test_dashboard_tasks_and_ics(client, auth, meeting):
    make_tasks(client, auth, meeting)
    d = client.get("/api/dashboard", headers=auth).json()
    assert d["counts"]["open_tasks"] == 5 and d["counts"]["overdue_tasks"] == 1
    assert {t["title"] for t in d["due_soon_tasks"]} == {"기한 지남", "알림 꺼짐", "내일 마감"}
    r = client.get(f"/api/meetings/{meeting['id']}/ics", headers=auth)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert "DTSTART:20301110T050000Z" in r.text and "ATTENDEE;CN=김개발:mailto:dev@test.com" in r.text


def test_openai_result_analysis(client, auth, meeting):
    import json
    from types import SimpleNamespace

    from app.services.ai import set_provider_override
    from app.services.ai.openai_provider import OpenAIProvider

    reply = {"summary": "요약", "decisions": ["범위 확정"], "undecided": [], "further_discussion": [],
             "tasks": [{"title": "API 테스트", "description": "", "assignee_name": "김개발님", "due_date": "2030-11-20", "due_text": "11월 20일",
                        "priority": "high", "uncertain": False, "evidence": "김개발: API 테스트"},
                       {"title": "견적", "assignee_name": "", "due_date": "null", "priority": "medium"}]}
    p = OpenAIProvider.__new__(OpenAIProvider)
    p.model, p.max_chars = "m", 60000
    calls = []

    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))])

    p.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    set_provider_override(p)
    r = analyze(client, auth, meeting["id"]).json()
    assert r["source"] == "openai"
    t = r["draft_tasks"][0]
    assert t["assignee_name"] == "김개발" and t["assignee_participant_id"] == meeting["participants"][0]["id"]
    assert r["draft_tasks"][1]["due_date"] is None
    assert "2030-11-10(일요일)" in calls[0]["messages"][0]["content"]
