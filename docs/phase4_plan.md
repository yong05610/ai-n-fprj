# PaceMate Phase 4 — AI 학습 경로·계획 (PLAN)

**기준:** TASK.md Phase 4, docs/phase4_dev_prompt.md (검증팀 착수 프롬프트), PRD.md FR-02, docs/erd_current.md
**상태:** 2026-10-19 구현 완료 → 검증팀 1차 리뷰(조건부 보류, 결함 7건) 반영 완료, 재검증 대기 (실 LLM 미검증)

---

## 1. 착수 전 정리 (코드보다 먼저 처리)

- **push 상태:** 시작 시점에 로컬 커밋 2건(`b0a6e7e`, `010e062`)이 origin/main에 push되지 않은 상태였다. Phase 4 작업으로 추가 커밋이 쌓였으며, 아직 push하지 않았다 (push는 사용자 지시 시 진행).
- **PDF 파일:** `docs/` 안의 브라우저 저장 PDF는 작업 시작 시점에 이미 제거되어 있었다 (추가 조치 불필요).
- **문서 정렬:** PRD.md §6 필드명을 구현 이름(`field`/`course`/`current_level_order`/`target_date`/`content` 등) 기준으로 갱신했다. `docs/phase1_design.md`의 설계 ERD에 `users.active_goal_id`/`consent_version`, `goals`의 `*_level_order`·수준 설명 스냅샷, `study_logs.started_at`/`ended_at`을 반영했다. `docs/erd_current.md` 합의 사항 5번을 닫았다.
- **서비스 시간대:** `backend/clock.py`에 `SERVICE_TZ = Asia/Seoul`, `today()`, `week_monday()`를 추가했다. `target_date` 과거 검증과 계획 주간 기본값 계산이 모두 이 함수를 통해서만 "오늘"을 판정하도록 교체했다 (호스트가 UTC로 배포되어도 한국 기준 날짜로 판정). Windows에서 `zoneinfo`가 `Asia/Seoul`을 찾으려면 `tzdata` 패키지가 필요해 `requirements.txt`에 추가했다.

## 2. 열린 결정 (docs/phase4_dev_prompt.md 기준, 결정 및 근거)

### 결정 1 — 확정 전 저장 문제 (검증팀 권장안 채택)
`PlanGenerateRequest`에서 `goal_id`를 없앴다. 1단계 추천과 2단계 초안 생성은 아무것도 저장하지 않으며, 사용자가 편집을 마치고 확정할 때만 새 `POST /api/plan/confirm` 하나로 목표(`goals`)와 과제(`tasks`)를 함께 생성한다. 이것으로 PRD FR-02 "확정한 과정·수준·계획만 저장"을 지킨다. 저장은 모든 서버 검증(수준 순서, 목표일 범위, 주간 시간 총량)을 통과한 뒤에만 쓰기를 시작하므로, 유효성 검증 실패로 인한 부분 저장은 없다 (다만 저장소 계층에 여러 문서를 묶는 진짜 트랜잭션은 없음 — 검증-후-쓰기로 대체. 여러 Firestore 쓰기 도중 예기치 않은 인프라 장애가 나면 과제 일부만 저장될 수 있는 이론적 여지는 남아 있고, 실제 트랜잭션 배치는 추후 과제로 남긴다).

### 결정 2 — 목표 개수·active_goal_id
MVP는 사용자당 목표 개수를 제한하지 않는다. `active_goal_id`는 Phase 3와 동일하게 "아직 지정된 활성 목표가 없을 때만" 새로 만든 목표로 채운다 (기존 목표를 덮어쓰지 않는다). 여러 목표 중 활성 목표를 바꾸는 것은 기존 `PATCH /api/user/profile`로 가능하다. 화면 쪽에서 "학습 경로 만들기"는 항상 새 목표를 만드는 흐름이며, 기존 목표에 이어 붙이는 흐름은 Phase 4 범위 밖이다.

### 결정 3 — 같은 목표·같은 주간 재확정
`POST /api/plan/confirm`은 항상 새 목표를 생성한다(기존 목표에 과제를 추가하는 경로가 아니다). 따라서 같은 세션에서 확정을 두 번 누르면 별도의 목표가 두 개 생긴다. 이를 막는 중복 방지 로직(멱등키 등)은 Phase 4 범위에 넣지 않았다 — 저장 버튼은 성공 시 "저장됨" 화면으로 전환되어 같은 요청을 다시 보낼 UI 경로가 없고, 더블클릭 수준의 경쟁 상태 방지는 중요도가 낮다고 판단했다. 기존 목표의 주간 계획을 다시 생성하는 흐름(재생성·추가)은 Phase 5 이후 과제로 남긴다.

### 결정 4 — 수준 order 상한, 과정·수준 개수 상한
Phase 3 리뷰에서 정한 `ge=1, le=20`(과정 내 수준 개수)을 유지했다. 추천 과정 개수는 Pydantic으로 `max_length=10`을 새로 걸어 AI가 과도하게 많은 과정을 만들지 못하게 했다. 두 상한 모두 시스템 프롬프트(`backend/prompts.py`)에 명시해 모델이 그 안에서 생성하도록 유도했다.

## 3. 구현 범위

| 영역 | 파일 | 내용 |
|---|---|---|
| AI 클라이언트 | `backend/ai_client.py` | 공급자 독립적 재시도/검증 루프(`AIClient.generate`). 타임아웃은 재시도(최대 2회), 스키마/의미 검증 실패도 재시도, 연결 실패·미설정은 즉시 실패(재시도 안 함). `AIUnavailableError`/`AITimeoutError`/`AISchemaError`로 구분. `_LazyOpenAIClient`로 `Depends()` 해석 시점에 즉시 "키 없음" 에러가 터지지 않게 지연 초기화(검증 실패 요청이 AI를 부르기도 전에 503을 받는 버그를 막음) |
| AI 스키마 | `backend/ai_schemas.py` | AI 출력 전용 내부 스키마(`AIPathRecommendation`, `AIPlanDraft`). 공개 API DTO(`schemas.py`)와 분리해 AI가 ID·슬러그·출처를 직접 만들지 않게 함 |
| 프롬프트 | `backend/prompts.py` | 시스템 프롬프트 고정 상수. 사용자 입력은 항상 user 메시지의 JSON 데이터로만 전달하고, 그 안의 지시문은 따르지 않는다고 명시(프롬프트 주입 대비) |
| 참고자료 매칭 | `backend/resources_catalog.py` | `backend/data/rag_documents.json`(Phase 2 카탈로그, 수정하지 않음)의 `category`("분야 / 과정")를 분야·과정과 단순 부분일치. AI가 출처를 지어내지 않도록 전적으로 서버가 고정 카탈로그에서만 고른다 |
| 서비스 시간대 | `backend/clock.py` | `today()`, `week_monday()` — Phase 4·5 공용 |
| API | `backend/main.py` | `POST /api/path/recommend`, `POST /api/plan/generate`(초안만, 미저장), `POST /api/plan/confirm`(목표+과제 저장, 신규) 구현. `POST/PATCH /api/tasks`에 주간 시간 총량·목표일 범위 검증을 공유 함수로 추가(AI 경유 없이 저장하는 경로도 같은 규칙 적용) |
| 계약 | `backend/schemas.py` | `PathRecommendationResponse.courses[].levels[]`(과정별 수준), `suggested_roles`, `PlanGenerateRequest`(goal_id 제거, 수준 이름·설명 추가), `PlanConfirmRequest/Response` 신규 |
| 프론트 | `frontend/components/LearningPathWizard.tsx` | 분야/목표 입력 → 추천 → 과정 Chip(단일 선택, 1목표 1과정 결정과 일치) → 직무 Chip(단일 선택) → 현재/목표 수준 콤보(번호 미표시, 목표는 현재보다 높은 수준만) → 주당 시간·목표일·계획 주간 → 계획 생성 → 3탭(과제/조언/참고자료) 편집 → 확정 저장. 상태: 입력/요청 중/완료/오류, 오류 시 입력값 보존 |
| 공통 | `frontend/lib/api.ts` | 요청 타임아웃(AbortController, 기본 20초·AI 호출 45초). 명시적 재시도 버튼만 제공하고 자동 재시도는 넣지 않음(확정 저장 같은 쓰기 요청의 중복 실행을 피하기 위함) |

## 4. 검증 결과

- `backend/tests` 전체 102건 통과: Phase 3 범위 55건 + Phase 4 신규 47건(`test_phase4_plan.py` 32건, `test_ai_client.py` 13건, `test_deploy_guards.py`/계약 테스트 보강 포함).
- 테스트는 전부 가짜 AI 클라이언트(`FakeAIClient`, `app.dependency_overrides`)로 실행했다. 다룬 경로: 정상 성공, 스키마 위반 재시도 후 실패, 수준 순서 역전 재시도 후 실패, 직무명 5개 초과, 타임아웃 재시도 후 실패, 연결 실패(미재시도), 재시도 후 성공, 시간 총량 초과(조용히 자르지 않고 재시도 후 오류), 잘못된 요일 값, 자료 매칭/미매칭, 동의 전 403·토큰 없음 401, 목표 수준 역전·과거 목표일·월요일 아닌 주간·목표일 초과 주간 거부, 과제 생성/수정 시 주간 시간 총량 재검증, 확정 후 재조회, 타 UID 격리, 검증 실패 시 아무것도 저장되지 않음.
- 실제 서버 프로세스(`uvicorn`, dev 모드)를 띄워 `curl`/Python `urllib`로 실제 HTTP 왕복을 확인했다: `/health` 200, `/api/consent` 201, `/api/path/recommend`·`/api/plan/generate`가 `OPENAI_API_KEY` 미설정 상태에서 올바르게 `503 AI_UNAVAILABLE`로 응답(검증을 모두 통과한 뒤에만 AI를 호출한다는 점도 함께 확인), `/api/plan/confirm` 201로 저장되고 `GET /api/goals`로 재조회됨.
- 프론트: `npm run typecheck`, `npm run build` 통과.
- **미검증:** 실제 OpenAI 키로의 호출(선택적 스모크 테스트는 만들지 않음 — 키가 없어 작성해도 이번에 실행할 수 없음). 브라우저로 마법사 화면을 직접 조작하는 시각적 확인은 이 환경에 브라우저 자동화 도구가 없어 수행하지 못했다(위의 실제 서버 HTTP 왕복 확인과 `npm run build`가 대신한 근거). Firebase 실연동(Task 0.5)도 여전히 미검증이다.

## 4-1. 검증팀 2차 리뷰 결함 수정 (조건부 보류 → 수정)

모든 항목(P4-1, P4-2 필수 + P4-3~P4-7)을 이번 Phase 안에서 수정했다. 보류한 항목은 없다.

- **P4-1 [높음] 참고자료 오매칭:** `resources_catalog.match_references`를 분야 일치 필수로 바꿨다. 분야가 일치하지 않으면 과정 텍스트가 겹쳐도 더 이상 선택되지 않는다. 길이 3자 미만인 분야 입력("a", "AI" 등)은 아예 매칭하지 않는다(일반 단어·짧은 분야의 오탐 차단). 재현 시나리오 3건(UX 디자인/기초, Python/기초, "a")을 모두 포함한 회귀 테스트를 `backend/tests/test_resources_catalog.py`에 추가했다.
- **P4-2 [높음] 기본 계획 주간 시간대 오류:** `frontend/lib/week.ts`에 `mondayOfThisWeekKST()`를 추가해 `Intl.DateTimeFormat`으로 Asia/Seoul 날짜를 직접 읽고 UTC 변환 없이 월요일을 계산한다. 재현 시나리오(수요일 03:00 KST 등 00:00~09:00 KST 전 구간)를 Node 내장 테스트 러너(`node --test`, 신규 devDependency `tsx`)로 검증했다(`frontend/lib/week.test.ts`, `npm test`로 실행).
- **P4-3 [중] 저장 후 재조회 미표시:** 확정 성공 시 `GET /api/tasks?goal_id=&plan_week_start=`로 다시 불러와 완료 화면에 과제 목록을 표시한다.
- **P4-4 [중] 확정 중복 저장 가능성:** `PlanConfirmRequest.client_request_id`(선택)를 추가했다. 같은 UID·같은 값으로 재요청하면 새로 만들지 않고 기존 목표·과제를 200으로 반환한다(값을 생략하면 기존처럼 항상 새로 만든다 — 하위 호환). 프론트는 초안을 만들 때 요청 ID를 한 번 생성해 저장 재시도마다 재사용한다. 멱등성 테스트 3건 추가, 실제 서버(uvicorn)에 대고 같은 키로 두 번 호출해 목표가 1개만 남는 것을 직접 확인했다.
- **P4-5 [중] 과정·수준 이름 수정 불가:** 과정명·설명, 현재/목표 수준 이름·설명을 모두 입력란으로 바꿔 수정 가능하게 하고, 그 값이 계획 생성·확정 요청에 그대로 쓰인다.
- **P4-6 [중] 초안-입력 불일치:** 초안 생성에 쓰인 입력(과정명·수준·주당 시간·목표일·계획 주간)의 스냅샷을 `draftRecipeKey`로 저장해, 이후 해당 입력이 바뀌면 초안을 "최신 상태 아님"으로 표시하고 확정 버튼을 막는다. 과업 자체의 편집(제목/시간/요일)은 초안을 상하게 하지 않는다 — 스냅샷은 1단계 조건에만 걸려 있다.
- **P4-7 [중] 새로고침 시 초안 소실:** `frontend/lib/wizardStorage.ts`로 입력·초안·과제·요청 ID 전체를 `sessionStorage`에 저장하고 마운트 시 복원한다(저장 실패 시에도 동작, try/catch). 확정 성공 시 지운다. "← 홈으로"는 진행 중인 내용이 있으면 `window.confirm`으로 확인한다.

**경미한 사항 반영:**
- 서버·클라이언트 타임아웃 정렬: 서버 최악 재시도 시간(약 3×20초)보다 길게 클라이언트 AI 호출 타임아웃을 45초→70초로 올렸다.
- 수준이 1개뿐인 과정은 목표 수준 선택과 "계획 만들기" 버튼을 막고 안내 문구를 표시한다.
- 목표 완료일 입력에 `min`(오늘, Asia/Seoul)을 걸고, 계획 주간 입력은 월요일이 아니면 인라인 오류와 "이번 주 월요일로 설정" 버튼을 보여준다. 확정 버튼은 과업 시간이 0 이하이거나 제목이 비어 있으면 비활성화한다.
- `max_tokens` → `max_completion_tokens`로 교체(최신·추론 모델 호환), `requirements.txt`의 `openai`를 설치된 버전(`3.35.1`)으로 고정했다.
- AI 출력(과정·수준·과업·조언)에도 최종 저장 DTO와 같은 길이 제한을 추가해, AI가 한도를 넘는 텍스트를 내면 확정 단계가 아니라 AI 응답 검증 단계에서 재시도 후 오류로 처리되게 했다.
- **반영하지 않음(의도적 보류):** Firestore 배치 쓰기를 통한 목표+과제 완전 원자적 저장. 검증팀이 "경미"로 분류했고 현재는 검증-후-쓰기로 일반적인 실패 모드는 막혀 있다. 실제 Firestore 연동(Task 0.5) 전에는 진짜 트랜잭션 동작을 검증할 수도 없어, Firebase 연동 이후 과제로 남긴다.

**재검증:** backend 111건 통과(기존 102 + 결함 수정 9건), frontend `npm test` 6건 통과(P4-2 전용), `npm run typecheck`/`build` 통과. 실제 uvicorn 서버로 참고자료 매칭과 확정 멱등성을 다시 HTTP로 확인했다.

## 5. 참고

- 참고자료 카탈로그(`backend/data/rag_documents.json`)는 Phase 2에서 이미 검토·커밋된 원본이다. 처음 구현 중 실수로 스키마를 바꿔 덮어썼다가 `git status`로 발견해 되돌리고, 매칭 코드를 기존 스키마(`category`, `license`, `verified`, `chunks`)에 맞춰 다시 작성했다.
- `backend/.env.example`에 `OPENAI_MODEL`/`OPENAI_TIMEOUT_SECONDS`/`OPENAI_MAX_OUTPUT_TOKENS` 이름만 추가했다(값 없음).
- 사용자당 AI 호출 비용·남용 방지 제한은 넣지 않았다 — 베타 테스터 규모(5~8명)에서는 과도한 엔지니어링이라고 판단했다. 트래픽이 늘면 Phase 7 이후 과제로 재검토한다.
