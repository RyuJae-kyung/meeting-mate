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
│   │   ├── routers/             auth, meetings, materials, briefings, emails, dashboard
│   │   └── services/
│   │       ├── extraction.py    PDF/DOCX/PPTX/TXT 텍스트 추출 + 키워드
│   │       ├── briefing_service.py  공통/용어/개인 브리핑 생성 오케스트레이션
│   │       ├── ai/              base(인터페이스), openai_provider(실제), mock_provider(개발용)
│   │       ├── email/           providers(Resend/Mock), templates(HTML), dispatch(작업 처리·재시도)
│   │       ├── calendar/        Google Calendar 연동 확장 지점 (인터페이스만)
│   │       └── storage.py       업로드 파일 저장
│   ├── tests/                   pytest 통합 테스트 (실제 PostgreSQL 사용)
│   └── scripts/make_samples.py  시연용 샘플 자료 생성
├── frontend/                    React + Vite + TypeScript + Tailwind
│   └── src/
│       ├── api/                 axios 클라이언트, 타입
│       ├── lib/                 인증 컨텍스트, 날짜 포맷
│       ├── components/          레이아웃, 공통 UI, 편집기
│       └── pages/               로그인/가입, 대시보드, 회의 목록/생성/상세(탭), 개인 브리핑(공개), 설정
├── e2e/flow.js                  Playwright 브라우저 E2E
├── samples/                     샘플 회의 자료 4종
└── render.yaml                  Render 배포 Blueprint
```

## 2. 데이터베이스 관계 (현재 구현)

```
users 1───* meetings 1───* participants
                 │  1───* meeting_materials
                 │  1───* briefings ( participant_id NULL = 공통 브리핑, 값 = 참석자별 브리핑 ) *───1 participants
                 │  1───* glossary_terms
                 │  1───* email_jobs 1───* email_logs *───1 participants
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
| email_logs | meeting_id, participant_id, job_id, recipient, subject, body_html, status(sent/failed/retrying), provider(resend/mock), provider_message_id, error, attempts | 재시도는 같은 로그의 attempts 증가 |

### 다음 단계 테이블 (설계만, 미구현)

| 테이블 | 컬럼 | 관계 |
|---|---|---|
| questions | meeting_id, user_id, question, answer, citations(JSON: 파일명·위치), grounded(bool), source | meetings 1─* |
| meeting_results | meeting_id(unique), raw_text, source_file, summary, decisions(JSON), undecided(JSON), follow_ups(JSON), confirmed_at | meetings 1─1 |
| tasks | meeting_id, result_id, title, assignee_participant_id, assignee_name, due_date, priority(high/mid/low), status(todo/in_progress/done), reminder_sent_at | meetings 1─*, participants 1─* |

## 3. API 목록 (구현 완료)

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
| GET | /dashboard | 대시보드 데이터 | 로그인 |
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
