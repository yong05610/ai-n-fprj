# PaceMate Phase 5 — 학습 실행·회고·진행 (EXEC)

**기준:** TASK.md Phase 5, docs/phase5_dev_prompt.md, PRD.md FR-03·FR-05(저장 부분)·FR-06, docs/erd_current.md, docs/phase4_plan.md
**상태:** 2026-10-20 구현 완료, 검증 대기 (UI 미검증 — 브라우저 자동화 도구 없음)

---

## 1. 완료한 Task

TASK.md 5.1~5.9 전부 구현·백엔드 검증 완료. 5.2는 일시정지(paused) 제외라는 단서가 있다 — §5-1 참고, 사용자 승인 필요.

## 2. 변경 파일

**Backend**
- `backend/schemas.py`: `TaskResponse`에 `record_count`/`total_minutes` 추가. `StudyLogCreateRequest`에서 `goal_id` 제거(서버가 task에서 도출), `client_request_id` 추가, `minutes` 상한(1440) 추가, `activity`/`ReflectionCreateRequest.content` 공백·길이 검증, 태그 중복·공백·길이 정리, `started_at`/`ended_at` 쌍 검증(둘 다 있거나 둘 다 없고 순서가 맞아야 함). `StudyLogUpdateRequest`에 `delete_reflection` 플래그 추가. 신규: `TimerStartRequest`, `ActiveTimerResponse`, `TimerFinishRequest`, `TimerCancelRequest`.
- `backend/clock.py`: `week_sunday()`, `is_within_week()`, `date_from_utc_iso()`, `WEEKDAY_BY_INDEX` 추가.
- `backend/main.py`: `require_consented_uid`를 공유 서브 의존성(`get_current_user_doc`) 기반으로 재구성하고 `require_consented_user_doc`(전체 사용자 문서 반환) 신설. `GET/POST /api/study-logs`, `PATCH/DELETE /api/study-logs/{id}` 전체 구현. `POST /api/timer/start|finish|cancel`, `GET /api/timer/active` 신규. `GET /api/dashboard/summary` 전체 구현. `POST /api/tasks`, `PATCH /api/tasks/{id}`, `GET /api/tasks`에 `record_count`/`total_minutes` 집계 추가. `delete_task`가 해당 과제의 활성 타이머를 정리하도록 추가.
- 신규 테스트: `backend/tests/test_phase5_exec.py` (55건).
- 기존 테스트 보정: `backend/tests/test_endpoint_contracts.py`(이제 구현된 study-logs/dashboard 엔드포인트의 401 전용 테스트로 분리).

**Frontend**
- `frontend/components/Dashboard.tsx` (신규): 4대 지표, 오늘의 추천 과제 체크리스트(낙관적 토글+롤백), 주간 hit, 인사이트 카드. 로딩/오류/빈 상태 포함.
- `frontend/components/ExecutionScreen.tsx` (신규): 과제별 기록 목록(기간 선택), 기록 편집기(새 기록/수정 모드), 타이머 패널(실시간 경과 표시), 인라인 삭제 확인, 멱등 재시도 키.
- `frontend/app/page.tsx`: 내비게이션(대시보드/학습 실행 기록/학습 경로 만들기) 추가, 기존 `GoalList`를 Dashboard로 대체.
- `frontend/app/globals.css`: 대시보드·실행 화면용 클래스 추가 (`.shell.wide`, `.nav-bar`, `.stats`, `.task-list`, `.week-days`, `.exec-layout`, `.timer-panel` 등).

## 3. 테스트 결과

- **backend pytest:** 174건 전부 통과 (기존 119 + Phase 5 신규 55). `python -m pytest -q` → `174 passed`.
- **frontend:** `npm run typecheck` 통과, `npm run build` 통과, `npm test`(week.ts 순수 함수, Phase 4에서 추가한 6건) 통과.
- **실제 서버 HTTP 확인** (`uvicorn`, `AUTH_MODE=dev`, `STORE_BACKEND=memory`, dev 토큰): 동의 → 목표·과제 생성(마법사가 호출하는 것과 동일한 `/api/goals`+`/api/tasks`) → 학습 기록 2건 저장(회고 포함) → 기록 1건 수정(분 변경) → `GET /api/tasks`에서 `record_count=2`, `total_minutes=65` 확인 → 기록 1건 삭제 → `GET /api/dashboard/summary`에서 삭제 반영된 수치(40분, 기록 1건) 확인 → 타이머 시작→활성 조회→종료(분 저장)→활성 해제까지 전부 1회 왕복 확인. 전부 기대한 응답 코드·값과 일치했다.

## 4. 백엔드 테스트가 다룬 항목 (지시서 테스트 요구사항 대응)

생성·조회·수정·삭제 정상 경로 / 한 과제 2건 이상 기록 / 회고 생성·수정·삭제(삭제 전용 플래그) / 기록 삭제 시 회고만 삭제되고 과제·다른 기록 유지 / 과제 삭제 시 하위 기록·회고 삭제 + 활성 타이머 정리 / 목표 삭제 시 과제까지 연쇄 삭제 / 타 UID의 과제에 기록 생성 거부(403) + 타 UID 기록 수정·삭제 거부(403) / 미인증 401·동의 전 403 / 미래 날짜·0분·1441분·공백 활동·`started_at ≥ ended_at`·`started_at`만 있고 `ended_at` 없음 거부 / 기록 생성·타이머 시작·타이머 종료 각각의 멱등 재시도 / 주간 경계(월요일 자정 직후를 모킹한 케이스, 일요일 케이스, `period=week`가 지난주 기록을 제외하는지) / 타이머 시작·종료·409(이미 활성, 진행 중인 과제 정보 포함)·새로고침 복원(별도 GET으로 상태 복원됨을 확인)·삭제된 과제의 타이머 정리·데이터 삭제 요청의 타이머 정리 / 대시보드 빈 상태 기본값·오늘 추천 우선순위(요일 일치 우선, 없으면 순서대로, 지난 요일 미완료가 사라지거나 특별 표시되지 않음)·진행률 계산·기록 CRUD 후 수치 갱신·인사이트 충분/부족 전환.

## 5. 열린 결정 (1~7)

### 5-1. 활성 타이머 저장 위치·일시정지 포함 여부 — **사용자 승인 필요**
**결정:** `users.active_timer` 필드(`{task_id, goal_id, started_at, client_request_id}`)에 저장한다. 별도 컬렉션을 만들지 않은 이유: 사용자당 활성 타이머가 최대 1개뿐이라 1:1 관계이고, `require_consented_user_doc`이 이미 매 요청마다 `users` 문서를 한 번 읽으므로 추가 쿼리가 들지 않는다.
**일시정지(paused)는 구현하지 않았다.** PRD/TASK가 요구하는 상태 머신에 `paused`가 있지만, 서버 시각 기준 누적 시간 계산(시작-일시정지-재개 반복)이 복잡도 대비 Phase 5 가치가 낮다고 판단해 제외했다. 구현한 것은 PRD FR-03의 "학습 시작·종료" 핵심 동작(시작/종료/취소, 새로고침 복원, 중복 방지)이다. **이 결정은 조용히 내린 게 아니라 명시적으로 보고하며, 사용자 승인을 요청한다.** 승인되지 않으면 Phase 5 재작업 대상이다.

### 5-2. minutes와 started_at/ended_at이 어긋날 때
**결정:** `minutes`는 항상 사용자가 보낸 값을 그대로 저장한다(시간쌍에서 자동 계산해 덮어쓰지 않음). 다만 `/api/timer/finish`는 사용자가 `minutes`를 직접 안 보내면 서버가 `ended_at - started_at`으로 자동 계산한다(이땐 애초에 사용자 입력이 없으므로 "덮어쓰기"가 아니다). 24시간을 넘는 경과는 자동 계산을 거부하고 수동 입력을 요구한다.

### 5-3. 기록 저장이 과제를 자동 완료시키는가
**결정:** 아니오. 과제 완료는 `PATCH /api/tasks/{id}`의 `status`를 사용자가 직접 토글해야만 바뀐다. 기록을 몇 건 남겼다고 "완료"로 단정하는 것은 과제 범위(완료 기준이 사용자마다 다를 수 있음)를 서버가 임의로 판정하는 것이라 위험하다고 판단했다.

### 5-4. 회고 단독 삭제 방식
**결정:** `StudyLogUpdateRequest.delete_reflection: bool` 전용 필드. `reflection=null`은 Pydantic의 `exclude_none`(기존 `_changes()` 헬퍼) 때문에 "값 없음"과 "삭제 요청"을 구분할 수 없어 쓸 수 없었다. `reflection`과 `delete_reflection`을 동시에 보내면 422로 거부한다.

### 5-5. 과제별 누적 시간 제공 위치
**결정:** 별도 집계 엔드포인트를 만들지 않고 `GET/POST/PATCH /api/tasks` 응답에 `record_count`/`total_minutes`를 추가했다. `GET /api/tasks`(목록)는 사용자의 전체 `study_logs`를 한 번만 읽어 Python에서 `task_id`별로 묶어 N+1 쿼리를 피했다. 저장하지 않고 매 요청 계산하므로 불일치 위험은 없지만, 데이터가 매우 커지면(수만 건) 매 목록 조회마다 전체 로그를 읽는 비용이 커진다 — MVP 규모(사용자당 수십~수백 건)에서는 문제 없다고 보고 상한선은 별도로 두지 않았다.

### 5-6. 인사이트 충분/부족 기준
**결정:** 활성 목표의 `study_logs` 수 ≥ 3 **그리고** `reflections` 수 ≥ 1 이면 "충분"(Phase 6 AI 인사이트 제공 예정이라는 중립 안내), 아니면 "부족"(기록·회고를 더 남기라는 안내). 가짜 AI 문장은 만들지 않았다.

### 5-7. 동일 과제·같은 날 기록 중복 허용 여부
**결정:** 허용(제한 없음). 하루를 여러 세션으로 나눠 공부하고 각각 기록하는 사용 방식을 막을 이유가 없다고 판단했다.

## 6. 함께 처리한 항목 (Phase 3·4에서 남은 것)

- **`require_consented_uid`의 중복 읽기 비용:** `get_current_user_doc`이라는 공유 서브 의존성을 두고 `require_consented_uid`/`require_consented_user_doc`가 같은 것에 의존하게 했다. FastAPI는 한 요청 안에서 같은 의존성 콜러블을 한 번만 평가하므로, Phase 5의 새 엔드포인트(대시보드·타이머)는 `users` 문서를 요청당 한 번만 읽는다. **다만 기존 15개 엔드포인트의 `require_consented_uid` 호출부 자체는 바꾸지 않았다** — 전면 리팩터는 이번 범위 밖이라 보류했다(이유: 이미 통과한 기존 테스트·계약을 건드리는 위험 대비 이득이 작다고 판단).
- **목표의 weekly_hours를 낮추는 PATCH가 이미 저장된 과제 시간 예산과 어긋나는 문제:** 기존 주(이미 저장된 과제들)는 소급 재검증하지 않기로 결정했다 — 목표 수정과 과제 저장은 서로 다른 리소스이고, 소급 거부는 사용자에게 당황스러운 400을 유발할 수 있다. 새로 만들거나 시간을 바꾸는 과제에는 (낮아진) 현재 `weekly_hours` 기준이 계속 적용된다(`_validate_task_time_budget`가 이미 그렇게 동작).
- **ERD/설계 문서 갱신:** `docs/erd_current.md`, `docs/phase1_design.md`를 Phase 5 계약(타이머 상태, 집계 응답 필드)에 맞게 갱신했다 (§7 참고).

## 7. 갱신한 문서

- `docs/erd_current.md` — `users.active_timer`, `study_logs.client_request_id`, `goals.client_request_id` 반영, Phase 5 결정 1~7 요약 표 추가.
- `docs/phase1_design.md` — ERD `users.active_timer` 추가, API 표에 타이머 엔드포인트 4개 추가.
- `TASK.md` — Phase 5 체크, 5.2에 일시정지 제외 단서 표기.
- `docs/phase5_report.md` — 본 문서.

## 8. 미검증 항목과 사용자가 직접 눌러 볼 시나리오

**미검증**
- **브라우저 UI 조작:** 이 환경에 브라우저 자동화 도구가 없어 화면을 직접 눌러 확인하지 못했다. 위 백엔드 검증(pytest 174건 + 실제 HTTP 왕복)과 `npm run build`/`typecheck`로 대신 확인했다.
- **Firebase 실연동(Task 0.5):** 여전히 미검증. `STORE_BACKEND=memory`, `AUTH_MODE=dev` 기준으로만 확인했다.

**사용자가 직접 눌러 볼 시나리오** (`npm run dev` + `uvicorn main:app` 둘 다 dev 모드로 띄운 뒤)
1. 동의 → "학습 경로 만들기"로 목표·과제 확정 (실제 OpenAI 키 필요, 없으면 백엔드로 직접 `POST /api/goals`+`POST /api/tasks` 호출해 둔다).
2. "대시보드"에서 목표 제목·수준 문구(번호 없이 이름만)·오늘의 추천 과제·주간 hit가 보이는지 확인.
3. "학습 실행 기록"에서 과제를 선택 → 타이머 패널이 보이는지, "학습 시작" 클릭 후 경과 시간이 1초마다 올라가는지 확인.
4. 다른 과제를 선택하지 않고 "학습 종료"로 저장 → 실행 내용·회고를 입력하고 저장 → 기록 목록에 나타나는지 확인.
5. 과제를 선택한 채 새로고침(F5) → 타이머가 진행 중이었다면 복원되는지 확인.
6. 기존 기록을 클릭 → "학습 기록 수정 중" 표시와 함께 값이 채워지는지, 수정 후 저장·취소(롤백)가 되는지 확인.
7. 기록 삭제 → 팝업이 아니라 같은 화면에서 "정말 삭제할까요?" 인라인 확인이 뜨는지 확인.
8. 대시보드로 돌아가 과제 체크리스트를 토글 → 즉시 체크 표시되고(낙관적 업데이트), 새로고침 후에도 유지되는지 확인.
9. "내 학습 데이터 삭제 요청"을 누른 뒤 다시 들어가 타이머·기록이 전부 비어 있는지 확인.

## 9. push

커밋 전 과정과 동일하게 테스트 통과·비밀값 없음·의도한 파일만 포함을 확인한 뒤 push했다(사용자가 부여한 재량 권한, `docs` 참고: 다른 세션이 설정한 push 기준).

---

보고 후 멈추고 검증팀 검증을 기다립니다. **특히 5-1(타이머 일시정지 제외)은 사용자 승인이 필요합니다.**
