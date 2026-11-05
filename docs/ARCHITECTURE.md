# Meeting Mate 설계 문서

## 1. 전체 구조

```
meeting-mate/
├── backend/                     FastAPI + SQLAlchemy + PostgreSQL
│   ├── app/
│   │   ├── main.py              앱 생성, CORS, 예외 처리, 라우터 등록, 스케줄러 시작
│   │   ├── config.py            환경변수 설정 (pydantic-settings)
│   │   ├── database.py          엔진/세션
│   │   ├── models.py            ORM 모델 (테이블)
│   │   ├── schemas.py           요청/응답 + AI 결과 검증 스키마
│   │   ├── security.py          bcrypt 비밀번호 해시, JWT
│   │   ├── deps.py              인증/회의 접근 권한 의존성
│   │   ├── scheduler.py         APScheduler (예약 이메일 처리)
│   │   ├── migrations.py        기존 DB에 새 컬럼을 추가하는 멱등 보정
│   │   ├── routers/             auth, meetings, materials, briefings, emails, questions, results, tasks, dashboard
│   │   └── services/
│   │       ├── extraction.py    PDF/DOCX/PPTX/TXT 텍스트 추출 + 키워드
│   │       ├── briefing_service.py  공통/용어/개인 브리핑 생성 오케스트레이션
│   │       ├── retrieval.py     질의응답용 자료 검색 (한글 2글자 단위 + TF-IDF)
│   │       ├── qa_service.py    자료 기반 질의응답 (출처 검증)
│   │       ├── result_service.py  회의 결과 분석 초안 → 확정 → 업무 생성
│   │       ├── task_reminders.py  후속 업무 마감 임박 알림
│   │       ├── dates.py         '다음 주 금요일' 같은 한국어 마감 표현 해석
│   │       ├── ai/              base(인터페이스), openai_provider(실제), mock_provider(개발용)
│   │       ├── email/           providers(Resend/Mock), templates(HTML), dispatch(작업 처리·재시도)
│   │       ├── calendar/        .ics 내보내기 + Google Calendar 연동 확장 지점(인터페이스)
│   │       └── storage.py       업로드 파일 저장
│   ├── tests/                   pytest 통합 테스트 (실제 PostgreSQL 사용)
│   └── scripts/make_samples.py  시연용 샘플 자료 생성
├── frontend/                    React + Vite + TypeScript + Tailwind
│   └── src/
│       ├── api/                 axios 클라이언트, 타입
│       ├── lib/                 인증 컨텍스트, 날짜 포맷
│       ├── components/          레이아웃, 공통 UI, 편집기
│       └── pages/               로그인/가입, 대시보드, 회의 목록/생성/상세(탭 8개), 업무 관리, 개인 브리핑(공개), 설정
├── e2e/flow.js                  Playwright 브라우저 E2E
├── samples/                     샘플 회의 자료 4종
└── render.yaml                  Render 배포 Blueprint
```

## 2. 데이터베이스 관계

```
users 1───* meetings 1───* participants
  │              │  1───* meeting_materials
  │              │  1───* briefings ( participant_id NULL = 공통 브리핑, 값 = 참석자별 브리핑 ) *───1 participants
  │              │  1───* glossary_terms
  │              │  1───* email_jobs 1───* email_logs *───1 participants
  │              │                          *───1 tasks   (업무 알림 메일)
  │              │  1───1 meeting_results
  │              │  1───* tasks *───1 participants (담당자, 참석자가 아니면 NULL + 이름만)
  └──────────────┴─ 1───* questions (질문한 사용자)
```

| 테이블 | 주요 컬럼 | 비고 |
|---|---|---|
| users | email(unique), password_hash, name, job_title, role(member/admin), email_notifications | 관리자는 `ADMIN_EMAILS` 로 지정 |
| meetings | owner_id→users, title, purpose, start_at/end_at(timestamptz), location, online_url, agenda, status(scheduled/ready/completed), external_calendar_id | 삭제 시 하위 데이터 CASCADE |
| participants | meeting_id→meetings, name, email, role, responsibility, access_token(unique) | (meeting_id, email) unique. access_token = 로그인 없는 개인 브리핑 링크 |
| meeting_materials | meeting_id, original_filename, stored_path, file_type, size_bytes, status, error, extracted_text, segments(JSON: 위치별 텍스트), title, summary, summary_source, keywords | segments의 loc(p.N / 슬라이드 N / 문단 N / 표 N)로 출처 표시 |
| briefings | meeting_id, participant_id(nullable)→participants, content(JSON), source(openai/mock), model, is_edited | 항목마다 basis(fact/inference/uncertain) + source |
| glossary_terms | meeting_id, term, easy_explanation, work_meaning, related_concepts, context, source_ref, why_important, is_uncertain, source | |
| email_jobs | meeting_id, created_by, participant_ids, mode(now/scheduled/before_meeting), minutes_before, scheduled_at, status | 즉시 발송도 job으로 처리 → 원자적 선점 |
| email_logs | meeting_id, participant_id, job_id, task_id, email_type(briefing/task_reminder), recipient, subject, body_html, status(sent/failed/retrying), provider(resend/mock), provider_message_id, error, attempts | 재시도는 같은 로그의 attempts 증가 |
| questions | meeting_id, user_id, question, answer, grounded(materials/partial/none), citations(JSON: file·loc·quote), general_knowledge, source | 본인 질문만 조회 |
| meeting_results | meeting_id(unique), raw_text, source_filename, summary, decisions, undecided, further_discussion, draft_tasks(JSON), status(draft/confirmed), confirmed_at, source | AI 초안은 draft_tasks 에만 두고 확정 시 tasks 생성 |
| tasks | meeting_id, created_by, title, description, assignee_participant_id, assignee_name, assignee_email, due_date, priority(high/medium/low), status(todo/in_progress/done), from_ai, reminder_enabled, reminder_sent_at, completed_at | 담당자 이메일로 '내 업무' 조회·상태 변경 |

기존(이전 버전) DB에는 `app/migrations.py`가 서버 시작 시 `email_logs.task_id` 컬럼을 추가합니다.

## 3. API 목록

모든 API는 `/api` 접두사. 인증: `Authorization: Bearer <JWT>` (공개 브리핑 제외). 오류 응답은 `{"detail": "한국어 메시지"}`.
상세 스키마는 서버 실행 후 `/docs` (Swagger UI).

| Method | Path | 설명 | 권한 |
|---|---|---|---|
| POST | /auth/register | 회원가입 → 토큰 | - |
| POST | /auth/login | 로그인 → 토큰 | - |
| GET/PUT | /auth/me | 내 정보 조회/수정 | 로그인 |
| PUT | /auth/password | 비밀번호 변경 | 로그인 |
| GET | /meetings?status=&q= | 내가 만든 + 초대된 회의 목록 | 로그인 |
| POST | /meetings | 회의 생성 (참석자 포함) | 로그인 |
| GET | /meetings/{id} | 회의 상세 | 열람 |
| PUT / DELETE | /meetings/{id} | 수정 / 삭제 | 편집 |
| PATCH | /meetings/{id}/status | 상태 변경 | 편집 |
| POST | /meetings/{id}/participants | 참석자 추가 | 편집 |
| PUT / DELETE | /participants/{pid} | 참석자 수정 / 삭제 | 편집 |
| POST | /meetings/{id}/materials | 자료 업로드(multipart `files`, 최대 10개) + 추출·분석 | 편집 |
| GET | /meetings/{id}/materials | 자료 목록 | 열람 |
| GET | /materials/{mid} | 자료 상세(추출 텍스트·위치별 조각) | 열람 |
| POST | /materials/{mid}/reanalyze | 재분석 | 편집 |
| DELETE | /materials/{mid} | 삭제 | 편집 |
| POST | /meetings/{id}/briefings/generate | 공통 브리핑 + 전문 용어 + 참석자별 브리핑 생성 | 편집 |
| GET | /meetings/{id}/briefing | 공통 브리핑 | 열람 |
| PUT | /briefings/{bid} | 브리핑 수정(스키마 검증) | 편집 |
| GET | /meetings/{id}/participant-briefings | 참석자별 브리핑 (참석자는 본인 것만) | 열람 |
| POST | /participants/{pid}/briefing/regenerate | 개인 브리핑 재생성 | 편집 |
| GET | /meetings/{id}/glossary | 전문 용어 목록 | 열람 |
| PUT / DELETE | /glossary/{tid} | 용어 수정 / 삭제 | 편집 |
| GET | /public/briefings/{token} | 개인 브리핑 공개 링크 (로그인 불필요) | 토큰 |
| POST | /meetings/{id}/emails/preview | 참석자별 이메일 미리보기 | 편집 |
| POST | /meetings/{id}/emails/send | 발송 (`confirm: true` 필수, mode=now/scheduled/before_meeting) | 편집 |
| GET | /meetings/{id}/emails/logs | 발송 내역 | 편집 |
| GET | /meetings/{id}/emails/jobs | 발송 작업(예약) 목록 | 편집 |
| GET | /emails/logs/{lid} | 발송 본문 | 편집 |
| POST | /emails/logs/{lid}/retry | 실패 건 재시도 | 편집 |
| POST | /emails/jobs/{jid}/cancel | 예약 취소 | 편집 |
| GET | /meetings/{id}/ics | 회의 일정 .ics 내보내기 (Google Calendar·Outlook 가져오기) | 열람 |
| POST | /meetings/{id}/questions | 자료 기반 질문 → 답변·출처 | 열람 |
| GET | /meetings/{id}/questions | 내 질문 기록 | 열람 |
| DELETE | /questions/{qid} | 내 질문 삭제 | 본인 |
| GET | /meetings/{id}/result | 회의 결과 (초안 또는 확정) | 열람 |
| POST | /meetings/{id}/result/analyze | 회의 내용 텍스트(`text`)·회의록 파일(`file`) 분석 → 초안 (업무는 아직 생성 안 함) | 편집 |
| POST | /meetings/{id}/result/confirm | 사용자가 수정한 결과 확정 + 업무 생성 | 편집 |
| GET | /tasks?scope=all\|mine&status=open\|todo\|in_progress\|done&due=soon\|overdue&meeting_id=&assignee= | 업무 목록 | 로그인 |
| POST | /meetings/{id}/tasks | 업무 직접 추가 | 편집 |
| PUT / DELETE | /tasks/{tid} | 업무 수정 / 삭제 | 편집 |
| PATCH | /tasks/{tid}/status | 진행 상태 변경 | 편집 또는 담당자 본인 |
| POST | /tasks/{tid}/remind | 담당자에게 지금 알림 발송 | 편집 |
| GET | /dashboard | 대시보드 데이터 (회의·발송·미완료/마감 임박 업무) | 로그인 |
| GET | /system/status | AI/이메일/스케줄러 연동 상태 | 로그인 |
| GET | /health | 헬스체크(DB 포함) | - |

권한: **열람** = 생성자·관리자·참석자로 등록된 이메일의 사용자, **편집** = 생성자·관리자. 권한 없는 회의는 존재 여부를 숨기기 위해 404.

## 4. 핵심 설계 결정

- **사실/추론 구분**: 모든 브리핑 항목은 `{text, basis: fact|inference|uncertain, source}`. OpenAI 프롬프트에 근거 원칙을 명시하고, 응답은 JSON 모드 + Pydantic 스키마로 검증. 형식이 틀리면 저장하지 않고 502.
- **Mock vs 실제**: 키가 없으면 Mock으로 동작하되 DB `source="mock"`, 화면 `MOCK AI` 배지, 이메일 제목 `[MOCK]`·배너, 발송 로그 `provider="mock"`으로 구분.
- **AI 실패 시 기존 결과 보존**: 생성 결과를 모두 받은 뒤 한 트랜잭션으로 교체.
- **이메일 중복 방지**: 발송은 모두 `email_jobs` 행으로 만들고 `UPDATE ... WHERE status='pending'` 원자적 선점에 성공한 프로세스만 발송. 재시도도 `failed→retrying` 선점. APScheduler는 `max_instances=1, coalesce=True`. 처리 중 서버가 죽은 작업은 자동 재발송하지 않고 실패로 표시.
- **사용자 확인**: 발송 API는 `confirm=true` 없이는 거부, UI는 미리보기 → 수신자 확인 체크 → 발송.
- **파일 검증**: 확장자 화이트리스트, 용량 제한, 시그니처(%PDF, ZIP 내부 구조) 검사, 저장 파일명은 UUID.
- **질의응답 근거**: 업로드 자료 + 회의 정보 + AI 브리핑을 조각(S1, S2…)으로 나눠 검색해 프롬프트에 넣고, AI가 인용한 번호를 실제 조각에 대응시켜 출처를 만든다. 존재하지 않는 번호는 버리고, 인용이 없으면 '자료 근거'로 표시하지 않는다. AI 브리핑만 인용하면 '자료 + 일반 지식'으로 낮춘다. 일반 지식 설명은 별도 필드로 분리.
- **회의 결과 → 업무**: AI 분석은 초안(draft)만 저장하고, 사용자가 담당자·마감일·우선순위를 확인·수정해 확정해야 업무가 생성된다. 담당자 이름은 참석자와 자동 매칭하고, 참석자가 아니거나 마감일이 불분명하면 '확인 필요'로 표시. 마감 표현은 회의일 기준으로 해석(주는 월요일 시작).
- **마감 알림**: 미완료·알림 켜짐·담당자 이메일 있음·오늘 ≤ 마감일 ≤ 오늘+N일·미발송 업무만 대상. `reminder_sent_at IS NULL` 원자적 선점으로 1회만 발송. 담당자가 가입 사용자이고 설정에서 알림을 끈 경우 제외. 마감일을 바꾸면 다시 발송 가능. 기한이 이미 지난 업무에는 자동 발송하지 않는다(수동 '알림'은 가능).
