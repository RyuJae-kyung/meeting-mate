"""브리핑 이메일 HTML 렌더링 (이메일 클라이언트 호환을 위해 인라인 스타일 사용)."""
from html import escape

from ...config import get_settings
from ...models import Briefing, GlossaryTerm, Meeting, Participant
from ..timefmt import fmt_range

BASIS_LABEL = {"fact": ("자료 근거", "#0f766e", "#ccfbf1"), "inference": ("AI 추론", "#6d28d9", "#ede9fe"), "uncertain": ("확인 필요", "#b45309", "#fef3c7")}


def _badge(basis: str) -> str:
    label, fg, bg = BASIS_LABEL.get(basis, BASIS_LABEL["inference"])
    return f'<span style="display:inline-block;font-size:11px;padding:1px 6px;border-radius:4px;color:{fg};background:{bg};margin-right:6px">{label}</span>'


def _items(items: list[dict]) -> str:
    if not items:
        return '<p style="color:#6b7280;font-size:14px;margin:4px 0">해당 내용 없음</p>'
    lis = []
    for it in items:
        src = f' <span style="color:#9ca3af;font-size:12px">({escape(it["source"])})</span>' if it.get("source") else ""
        lis.append(f'<li style="margin:6px 0;font-size:14px;line-height:1.55">{_badge(it.get("basis", "inference"))}{escape(it.get("text", ""))}{src}</li>')
    return f'<ul style="padding-left:18px;margin:4px 0">{"".join(lis)}</ul>'


def _h(title: str) -> str:
    return f'<h3 style="font-size:15px;margin:22px 0 6px;color:#111827;border-bottom:1px solid #e5e7eb;padding-bottom:4px">{escape(title)}</h3>'


def personal_link(p: Participant) -> str:
    return f"{get_settings().FRONTEND_URL.rstrip('/')}/b/{p.access_token}"


def render_briefing_email(meeting: Meeting, p: Participant, personal: Briefing, general: Briefing | None, glossary: list[GlossaryTerm]) -> tuple[str, str]:
    is_mock = personal.source == "mock"
    subject = f"[Meeting Mate] {meeting.title} 사전 브리핑 · {fmt_range(meeting.start_at, meeting.end_at)}"
    if is_mock:
        subject = "[MOCK] " + subject
    pc = personal.content
    related = set(t.lower() for t in pc.get("related_terms", []))
    terms = [g for g in glossary if g.term.lower() in related] or glossary[:5]
    place = escape(meeting.location or "")
    if meeting.online_url:
        url = escape(meeting.online_url)
        place += (" · " if place else "") + f'<a href="{url}" style="color:#4f46e5">{url}</a>'
    agenda = "".join(f'<li style="margin:3px 0;font-size:14px">{escape(a)}</li>' for a in meeting.agenda_items) or "<li>미입력</li>"
    glossary_html = "".join(
        f'<div style="margin:8px 0;padding:8px 10px;background:#f9fafb;border-radius:6px;font-size:14px"><b>{escape(g.term)}</b>'
        f'{" <span style=\"color:#b45309;font-size:12px\">(확인 필요)</span>" if g.is_uncertain else ""}<br>'
        f'<span style="color:#374151">{escape(g.easy_explanation)}</span>'
        f'{"<br><span style=\"color:#6b7280;font-size:13px\">실무 의미: " + escape(g.work_meaning) + "</span>" if g.work_meaning else ""}</div>'
        for g in terms
    ) or '<p style="color:#6b7280;font-size:14px">추출된 용어 없음</p>'
    checklist = (general.content.get("checklist", []) if general else []) + pc.get("preparation", [])
    mock_banner = (
        '<div style="background:#fef3c7;color:#92400e;padding:8px 12px;border-radius:6px;font-size:13px;margin-bottom:12px">'
        "이 브리핑은 개발용 Mock AI로 생성되었습니다. 실제 AI 분석 결과가 아닙니다.</div>" if is_mock else ""
    )
    link = escape(personal_link(p))
    html = f"""<!doctype html><html><body style="margin:0;background:#f3f4f6;font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;color:#111827">
<div style="max-width:640px;margin:0 auto;padding:24px 16px">
<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;padding:24px">
<div style="font-size:12px;color:#6b7280;margin-bottom:4px">Meeting Mate · 회의 사전 브리핑</div>
<h2 style="margin:0 0 12px;font-size:20px">{escape(meeting.title)}</h2>
{mock_banner}
<p style="margin:0 0 4px;font-size:14px"><b>일시</b> {escape(fmt_range(meeting.start_at, meeting.end_at))}</p>
{f'<p style="margin:0 0 4px;font-size:14px"><b>장소</b> {place}</p>' if place else ''}
<p style="margin:12px 0 0;font-size:14px">{escape(p.name)}님 ({escape(p.role or '참석자')}), 회의 전에 아래 내용을 확인해 주세요.</p>
{_h('회의 목적')}<p style="font-size:14px;line-height:1.55;margin:4px 0">{escape(meeting.purpose or '미입력')}</p>
{_h('주요 안건')}<ol style="padding-left:18px;margin:4px 0">{agenda}</ol>
{_h('나를 위한 브리핑')}<p style="font-size:14px;line-height:1.55;margin:4px 0">{escape(pc.get('focus_summary', ''))}</p>
<p style="font-size:13px;color:#6b7280;margin:10px 0 2px">본인에게 중요한 안건</p>{_items(pc.get('key_agenda', []))}
<p style="font-size:13px;color:#6b7280;margin:10px 0 2px">사전에 확인할 자료</p>{_items(pc.get('materials_to_review', []))}
<p style="font-size:13px;color:#6b7280;margin:10px 0 2px">예상 질문</p>{_items(pc.get('expected_questions', []))}
{_h('알아두면 좋은 용어')}{glossary_html}
{_h('사전 준비 체크리스트')}{_items(checklist)}
<div style="margin-top:24px;text-align:center"><a href="{link}" style="display:inline-block;background:#4f46e5;color:#ffffff;text-decoration:none;padding:10px 18px;border-radius:6px;font-size:14px">개인 브리핑 전체 보기</a></div>
<p style="font-size:12px;color:#9ca3af;margin-top:20px;line-height:1.5">'자료 근거'는 회의 자료/정보에 명시된 내용, 'AI 추론'은 예상 내용, '확인 필요'는 불확실한 내용입니다. AI 추론은 회의에서 결정된 사항이 아닙니다.</p>
</div></div></body></html>"""
    return subject, html


PRIORITY_LABEL = {"high": "높음", "medium": "보통", "low": "낮음"}
STATUS_LABEL = {"todo": "대기", "in_progress": "진행 중", "done": "완료"}


def render_task_reminder(task, meeting: Meeting, today) -> tuple[str, str]:
    days = (task.due_date - today).days if task.due_date else None
    when = "오늘 마감" if days == 0 else (f"마감 {days}일 전" if days and days > 0 else f"마감 {abs(days)}일 지남" if days else "마감일 미정")
    subject = f"[Meeting Mate] 후속 업무 알림 · {task.title} ({when})"
    base = get_settings().FRONTEND_URL.rstrip("/")
    due = task.due_date.strftime("%Y년 %m월 %d일") if task.due_date else "미정"
    desc = f'<p style="font-size:14px;color:#374151;margin:8px 0">{escape(task.description)}</p>' if task.description else ""
    html = f"""<!doctype html><html><body style="margin:0;background:#f3f4f6;font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;color:#111827">
<div style="max-width:560px;margin:0 auto;padding:24px 16px"><div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:24px">
<div style="font-size:12px;color:#6b7280">Meeting Mate · 후속 업무 마감 알림</div>
<h2 style="margin:6px 0 4px;font-size:19px">{escape(task.title)}</h2>
<p style="margin:0 0 14px;font-size:13px;color:#b45309;font-weight:600">{escape(when)}</p>
{desc}
<table style="font-size:14px;border-collapse:collapse;margin-top:8px">
<tr><td style="color:#6b7280;padding:3px 14px 3px 0">담당자</td><td>{escape(task.assignee_name or '-')}</td></tr>
<tr><td style="color:#6b7280;padding:3px 14px 3px 0">마감일</td><td>{due}</td></tr>
<tr><td style="color:#6b7280;padding:3px 14px 3px 0">우선순위</td><td>{PRIORITY_LABEL.get(task.priority, task.priority)}</td></tr>
<tr><td style="color:#6b7280;padding:3px 14px 3px 0">진행 상태</td><td>{STATUS_LABEL.get(task.status, task.status)}</td></tr>
<tr><td style="color:#6b7280;padding:3px 14px 3px 0">관련 회의</td><td>{escape(meeting.title)} ({escape(fmt_range(meeting.start_at, meeting.end_at))})</td></tr>
</table>
<div style="margin-top:22px;text-align:center"><a href="{escape(base)}/tasks" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:10px 18px;border-radius:6px;font-size:14px">업무 관리에서 확인하기</a></div>
<p style="font-size:12px;color:#9ca3af;margin-top:18px">이 알림은 회의 결과 확정 시 '마감 임박 알림'이 켜진 업무에 대해 한 번만 발송됩니다. 받지 않으려면 Meeting Mate 설정에서 이메일 알림을 끄세요.</p>
</div></div></body></html>"""
    return subject, html
