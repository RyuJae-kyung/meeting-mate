"""개발용 Mock AI 공급자.

OPENAI_API_KEY 없이도 전체 흐름을 테스트할 수 있도록, 실제 입력(회의 정보·자료 텍스트)을
규칙 기반으로 가공해 결과를 만든다. 생성 결과는 DB에 source="mock" 으로 저장되고
화면/이메일에 'Mock' 배지로 구분 표시된다. 실제 AI 분석 결과가 아니다.
"""
import re

from .base import MeetingCtx, ParticipantCtx

# 회의 자료에서 자주 등장하는 업무 용어 사전 (Mock 전용)
TERM_DICT: dict[str, tuple[str, str, list[str]]] = {
    "MES": ("제조 현장에서 생산 과정을 관리하고 생산 실적, 작업 상태 등을 확인하는 시스템", "생산 현황을 파악하고 제조 과정의 효율성을 관리하는 데 활용된다.", ["ERP", "SCM", "스마트팩토리"]),
    "ERP": ("기업의 회계, 인사, 구매, 재고 등 여러 업무 정보를 통합 관리하는 시스템", "부서별로 흩어진 데이터를 하나로 모아 업무 처리와 의사결정을 빠르게 한다.", ["MES", "SCM", "CRM"]),
    "API": ("서로 다른 프로그램이 정해진 방식으로 데이터를 주고받기 위한 연결 규칙", "시스템 간 연동 범위와 일정, 데이터 형식을 정할 때 기준이 된다.", ["API Gateway", "REST", "연동"]),
    "API Gateway": ("여러 서비스로 가는 API 요청을 한곳에서 받아 인증·라우팅·트래픽 제어를 하는 관문", "외부 시스템 연동 시 보안과 장애 관리를 일관되게 적용할 수 있다.", ["API", "인증", "마이크로서비스"]),
    "CRM": ("고객 정보와 영업·상담 이력을 관리하는 시스템", "고객별 진행 상황을 파악하고 영업 활동을 체계화하는 데 쓰인다.", ["ERP", "영업 파이프라인"]),
    "SCM": ("원자재 조달부터 생산, 배송까지 공급망 전체를 관리하는 체계", "재고·납기 리스크를 줄이고 공급 일정을 맞추는 데 활용된다.", ["ERP", "MES"]),
    "KPI": ("목표 달성 정도를 측정하기 위한 핵심 성과 지표", "프로젝트 성공 여부를 판단하는 기준이므로 측정 방법을 합의해야 한다.", ["OKR", "성과 관리"]),
    "OKR": ("목표(Objective)와 핵심 결과(Key Results)로 성과를 관리하는 방식", "팀 목표와 개인 업무의 연결을 확인할 때 쓰인다.", ["KPI"]),
    "ROI": ("투자한 비용 대비 얻는 이익의 비율", "예산 승인 여부를 판단하는 핵심 근거가 된다.", ["비용", "TCO"]),
    "TCO": ("도입부터 운영·유지보수까지 드는 총 소유 비용", "초기 비용만이 아닌 장기 운영 비용까지 비교할 때 필요하다.", ["ROI"]),
    "SaaS": ("설치 없이 인터넷으로 구독해 사용하는 소프트웨어 서비스", "구축형 대비 초기 비용과 운영 부담이 적지만 커스터마이징에 제약이 있을 수 있다.", ["클라우드", "구독"]),
    "SLA": ("서비스 제공자가 보장하는 품질 수준(가용성, 응답 시간 등)에 대한 약속", "장애 발생 시 책임 범위와 보상 기준을 정한다.", ["가용성", "계약"]),
    "MVP": ("핵심 기능만 담아 빠르게 출시하는 최소 기능 제품", "1차 출시 범위를 정할 때 무엇을 넣고 뺄지 판단하는 기준이다.", ["PoC", "로드맵"]),
    "PoC": ("본격 도입 전에 기술이나 아이디어가 실제로 가능한지 검증하는 작은 실험", "본 사업 진행 여부를 결정하기 위한 근거 자료가 된다.", ["MVP", "파일럿"]),
    "UI": ("사용자가 화면에서 보고 조작하는 버튼, 메뉴 등 화면 구성 요소", "화면 설계 검토와 수정 범위를 논의할 때 쓰인다.", ["UX"]),
    "UX": ("사용자가 서비스를 이용하며 느끼는 전반적인 경험", "사용 편의성 개선 방향을 정할 때 기준이 된다.", ["UI"]),
    "QA": ("제품이 요구 수준을 충족하는지 확인하는 품질 검증 활동", "출시 일정에 테스트 기간이 충분히 반영되었는지 확인해야 한다.", ["테스트", "버그"]),
    "CI/CD": ("코드 변경을 자동으로 빌드·테스트·배포하는 개발 자동화 체계", "배포 주기와 품질 관리 방식에 영향을 준다.", ["배포", "자동화"]),
    "SSO": ("한 번 로그인으로 여러 시스템을 함께 이용하는 통합 인증 방식", "사내 시스템 연동 시 계정·보안 정책을 맞춰야 한다.", ["인증", "보안"]),
    "RFP": ("발주처가 업체에 제안을 요청하며 요구사항을 정리한 제안요청서", "요구사항 범위와 평가 기준의 근거 문서다.", ["제안서", "입찰"]),
    "WBS": ("프로젝트 작업을 단계별·세부 업무 단위로 나눈 작업 분해 구조", "담당자와 일정을 배분하는 기준이 된다.", ["일정", "PM"]),
    "PM": ("프로젝트의 일정, 범위, 인력, 리스크를 총괄하는 프로젝트 관리자", "의사결정과 이슈 에스컬레이션의 창구가 된다.", ["WBS"]),
    "B2B": ("기업과 기업 간 거래", "고객이 기업이므로 계약·도입 절차가 길고 복잡할 수 있다.", ["B2C", "영업"]),
    "MOU": ("정식 계약 전 협력 의사를 문서로 확인하는 양해각서", "법적 구속력이 제한적이므로 이후 본 계약 조건을 별도로 확인해야 한다.", ["계약"]),
    "BOM": ("제품을 만드는 데 필요한 부품·자재 목록", "원가 산정과 생산 계획의 기초 자료다.", ["MES", "ERP"]),
    "IoT": ("센서 등 사물을 인터넷에 연결해 데이터를 주고받는 기술", "현장 데이터를 자동 수집하는 기반이 된다.", ["센서", "MES"]),
    "ETL": ("여러 곳의 데이터를 추출·변환해 한곳에 적재하는 데이터 처리 과정", "데이터 통합 일정과 품질 기준에 영향을 준다.", ["데이터 웨어하우스"]),
    "OCR": ("이미지나 스캔 문서 속 글자를 인식해 텍스트로 바꾸는 기술", "문서 자동화 범위와 인식 정확도를 확인해야 한다.", ["AI"]),
    "DB": ("데이터를 체계적으로 저장하고 조회하는 데이터베이스", "데이터 구조 변경은 연동 시스템 전체에 영향을 줄 수 있다.", ["SQL"]),
    "LLM": ("대량의 글을 학습해 문장을 이해하고 생성하는 대규모 언어 모델", "AI 기능의 정확도·비용·보안 정책을 함께 검토해야 한다.", ["AI", "프롬프트"]),
}

ROLE_FOCUS: list[tuple[tuple[str, ...], str, list[str]]] = [
    (("개발", "엔지니어", "developer", "backend", "frontend", "백엔드", "프론트"), "개발", ["API", "연동", "시스템", "개발", "서버", "데이터", "테스트", "구현", "기술", "DB", "배포"]),
    (("기획", "pm", "planner", "product", "po"), "기획", ["요구사항", "일정", "목적", "기획", "범위", "결정", "우선순위", "사용자"]),
    (("관리자", "팀장", "매니저", "manager", "임원", "본부장", "리더", "director"), "관리", ["비용", "예산", "일정", "리스크", "결정", "인력", "ROI", "승인"]),
    (("영업", "sales", "세일즈", "고객"), "영업", ["고객", "계약", "매출", "영업", "제안", "가격", "요구"]),
    (("디자인", "designer", "ux", "ui"), "디자인", ["UI", "UX", "화면", "디자인", "사용자", "사용성"]),
    (("qa", "테스트", "품질"), "품질", ["테스트", "QA", "품질", "버그", "검증"]),
]

ROLE_QUESTIONS = {
    "개발": ["현재 일정으로 구현이 가능한지, 기술적 제약은 무엇인지", "연동 대상 시스템의 인터페이스·데이터 형식이 확정되었는지", "테스트·배포 일정을 어떻게 잡을 것인지"],
    "기획": ["요구사항의 우선순위와 1차 범위를 어떻게 정할 것인지", "일정 지연 시 조정 가능한 항목은 무엇인지", "의사결정이 필요한 항목과 결정권자는 누구인지"],
    "관리": ["필요 예산과 인력 규모는 어느 정도인지", "주요 리스크와 대응 방안은 무엇인지", "오늘 결정해야 할 사항과 보류해도 되는 사항은 무엇인지"],
    "영업": ["고객의 핵심 요구사항이 반영되었는지", "계약 조건·납기에 영향을 주는 변경이 있는지", "고객에게 공유할 수 있는 진행 상황은 무엇인지"],
    "디자인": ["화면 변경 범위와 일정은 어떻게 되는지", "사용자 피드백이 반영되었는지"],
    "품질": ["테스트 범위와 완료 기준은 무엇인지", "알려진 결함과 출시 영향은 무엇인지"],
    "공통": ["담당 업무와 관련된 안건의 현재 진행 상황은 어떤지", "본인 업무에 영향을 주는 결정 사항이 있는지"],
}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|\n+", text)
    return [p.strip(" -•\t") for p in parts if len(p.strip()) >= 8]


def _find_context(ctx: MeetingCtx, pattern: re.Pattern, min_len: int = 15) -> tuple[str, str] | None:
    """패턴이 포함된 문장 중 제목줄처럼 짧은 문장보다 본문 문장을 우선 반환."""
    short: tuple[str, str] | None = None
    for m in ctx.materials:
        for seg in m.segments:
            for sent in _sentences(seg["text"]):
                if pattern.search(sent):
                    if len(sent) >= min_len:
                        return sent[:300], f"{m.filename} {seg['loc']}"
                    short = short or (sent[:300], f"{m.filename} {seg['loc']}")
    return short


def _term_pattern(term: str) -> re.Pattern:
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])")


def _role_profile(role: str, responsibility: str) -> tuple[str, list[str]]:
    hay = f"{role} {responsibility}".lower()
    for keys, label, focus in ROLE_FOCUS:
        if any(k in hay for k in keys):
            words = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", responsibility)][:5]
            return label, focus + words
    return "공통", [w for w in re.findall(r"[가-힣A-Za-z]{2,}", responsibility)][:6]


class MockProvider:
    name = "mock"
    model = "mock-rule-based"

    def summarize_material(self, filename: str, title: str | None, segments: list[dict]) -> str:
        sents: list[str] = []
        for seg in segments:
            sents.extend(_sentences(seg["text"]))
            if len(sents) >= 3:
                break
        body = " ".join(s[:200] for s in sents[:3]) or "(요약할 문장을 찾지 못했습니다)"
        return f"[Mock 요약 · 문서 앞부분 발췌] {body}"

    def generate_briefing(self, ctx: MeetingCtx) -> dict:
        all_kw: list[str] = []
        for m in ctx.materials:
            all_kw.extend(k for k in m.keywords if k not in all_kw)
        purpose = [{"text": ctx.purpose, "basis": "fact", "source": "회의 정보"}] if ctx.purpose else [
            {"text": "회의 목적이 입력되지 않았습니다. 주최자에게 목적을 확인하세요.", "basis": "uncertain", "source": None}
        ]
        agenda = [{"text": a, "basis": "fact", "source": "회의 안건"} for a in ctx.agenda_items]
        expected, questions, issues = [], [], []
        for a in ctx.agenda_items:
            words = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", a) if w not in ("검토", "확정", "논의", "대응", "관련")]
            hit = _find_context(ctx, re.compile("|".join(re.escape(w) for w in words[:2]))) if words else None
            if hit:
                expected.append({"text": f"'{a}' 관련 자료 내용: {hit[0]}", "basis": "fact", "source": hit[1]})
            expected.append({"text": f"'{a}'의 현재 진행 상황과 다음 단계에 대한 논의가 예상됩니다.", "basis": "inference", "source": None})
            questions.append({"text": f"'{a}'에 대해 이번 회의에서 결정해야 할 사항은 무엇인가요?", "basis": "inference", "source": None})
        if all_kw:
            issues.append({"text": f"자료에서 자주 언급된 '{', '.join(all_kw[:3])}' 관련 일정·범위·비용이 쟁점이 될 수 있습니다.", "basis": "inference", "source": None})
        issues.append({"text": "자료만으로는 이해관계자 간 이견 여부를 판단할 수 없습니다. 사전에 담당자와 확인이 필요합니다.", "basis": "uncertain", "source": None})
        checklist = [{"text": "회의 목적과 안건을 미리 읽고 본인 관련 안건을 표시하기", "basis": "inference", "source": None}]
        checklist += [{"text": f"'{m.filename}' 자료 검토하기", "basis": "fact", "source": m.filename} for m in ctx.materials]
        checklist.append({"text": "담당 업무의 현재 진행 상황과 이슈를 한두 줄로 정리해 가기", "basis": "inference", "source": None})
        summaries = []
        for m in ctx.materials:
            sents = []
            for seg in m.segments:
                sents.extend((s, seg["loc"]) for s in _sentences(seg["text"]))
                if len(sents) >= 2:
                    break
            if sents:
                summaries.append({"text": f"{m.filename}: " + " ".join(s for s, _ in sents[:2])[:400], "basis": "fact", "source": f"{m.filename} {sents[0][1]}"})
        if not ctx.materials:
            summaries.append({"text": "업로드된 회의 자료가 없습니다.", "basis": "uncertain", "source": None})
        return {
            "purpose_summary": purpose,
            "agenda_items": agenda or [{"text": "안건이 입력되지 않았습니다.", "basis": "uncertain", "source": None}],
            "expected_discussions": expected,
            "pre_questions": questions,
            "checklist": checklist,
            "issues": issues,
            "material_summaries": summaries,
        }

    def extract_glossary(self, ctx: MeetingCtx) -> list[dict]:
        found: list[dict] = []
        seen: set[str] = set()
        # 긴 용어부터 매칭 (API Gateway 가 API 보다 먼저)
        for term in sorted(TERM_DICT, key=len, reverse=True):
            hit = _find_context(ctx, _term_pattern(term))
            if not hit:
                continue
            easy, meaning, related = TERM_DICT[term]
            found.append({
                "term": term, "easy_explanation": easy, "work_meaning": meaning, "related_concepts": related,
                "context": hit[0], "source_ref": hit[1],
                "why_important": f"자료에서 '{term}'이(가) 언급되므로, 의미를 알고 있어야 관련 논의를 따라갈 수 있습니다.",
                "is_uncertain": False,
            })
            seen.add(term.upper())
        # 사전에 없는 대문자 약어는 '확인 필요'로 표시 (뜻을 지어내지 않음)
        acr = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,6})(?![A-Za-z0-9])")
        for m in ctx.materials:
            for seg in m.segments:
                for a in acr.findall(seg["text"]):
                    if a in seen or len(found) >= 15:
                        continue
                    seen.add(a)
                    hit = _find_context(ctx, _term_pattern(a))
                    found.append({
                        "term": a, "easy_explanation": "자료에서 정의를 찾을 수 없습니다. 회의 전 담당자에게 의미를 확인하세요.",
                        "work_meaning": "", "related_concepts": [], "context": hit[0] if hit else "",
                        "source_ref": hit[1] if hit else m.filename,
                        "why_important": "자료에 등장하는 약어로, 의미가 불확실합니다.", "is_uncertain": True,
                    })
        return found[:15]

    def personal_briefing(self, ctx: MeetingCtx, participant: ParticipantCtx, glossary_terms: list[str]) -> dict:
        label, focus = _role_profile(participant.role, participant.responsibility)
        focus_l = [f.lower() for f in focus]

        def relevant(text: str) -> bool:
            t = text.lower()
            return any(f in t for f in focus_l)

        key_agenda = [
            {"text": f"{a} — {participant.role or '본인'} 업무와 관련된 안건으로 보입니다.", "basis": "inference", "source": "회의 안건"}
            for a in ctx.agenda_items if relevant(a)
        ]
        if not key_agenda and ctx.agenda_items:
            key_agenda = [{"text": f"{ctx.agenda_items[0]} — 역할과 직접 연결된 안건을 찾지 못해 첫 안건을 표시합니다.", "basis": "uncertain", "source": "회의 안건"}]
        review: list[dict] = []
        for m in ctx.materials:
            for seg in m.segments:
                if relevant(seg["text"]) and len(review) < 4:
                    cands = [s for s in _sentences(seg["text"]) if relevant(s)]
                    sent = next((s for s in cands if len(s) >= 15), None)
                    if sent:
                        review.append({"text": sent[:300], "basis": "fact", "source": f"{m.filename} {seg['loc']}"})
        questions = [{"text": q, "basis": "inference", "source": None} for q in ROLE_QUESTIONS.get(label, ROLE_QUESTIONS["공통"])]
        prep = []
        if participant.responsibility:
            prep.append({"text": f"담당 업무('{participant.responsibility}')의 현재 진행 상황과 이슈 정리", "basis": "inference", "source": None})
        prep += [{"text": f"'{k['text'].split(' — ')[0]}' 안건에 대한 본인 의견 준비", "basis": "inference", "source": None} for k in key_agenda[:3]]
        text_all = " ".join(r["text"] for r in review) + " " + " ".join(ctx.agenda_items)
        related = [t for t in glossary_terms if _term_pattern(t).search(text_all)] or glossary_terms[:3]
        return {
            "focus_summary": f"[Mock] {participant.name}님은 '{participant.role or '참석자'}' 역할 기준으로 {label} 관점의 안건과 자료를 중심으로 준비하는 것이 좋습니다.",
            "key_agenda": key_agenda,
            "materials_to_review": review,
            "expected_questions": questions,
            "preparation": prep,
            "related_terms": related,
        }
