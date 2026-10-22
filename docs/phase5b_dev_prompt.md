# Phase 5B 개발팀 착수 프롬프트 (MULTI · 복수 학습 운용)

아래 전체를 개발팀(Backend/Frontend)에게 그대로 전달한다. 작성: PM(검증팀 겸임), 2026-10-22.

---

## 역할과 목표

너는 PaceMate 개발팀이다. TASK.md 의 **Phase 5B(B.1~B.8)만** 구현한다.
목표: 사용자가 여러 학습을 동시에 가질 수 있게 한다. 일정이 겹치는 새 학습은 만들 수 없고, 계획·실행 화면은 한 학습에 집중하되 작은 도구로 학습을 전환하며, 대시보드는 최근 학습과 종합 현황을 나누어 보여 주고, 종합 학습 분석 화면을 추가한다.

기준 문서(먼저 읽는다): docs/multi_goal_design.md(결정 원문), docs/erd_current.md("복수 학습 규칙"과 goals.start_date), docs/phase4_plan.md, docs/phase5_report.md, mockup/index.html(변경된 목업: 학습 전환 드롭다운 `goal-switch`, 대시보드 "종합 학습 현황", `page-analysis`, 튜터 안내문, 구현 상태 배지). 설계 문서와 목업은 PM 이 소유한다. 개발팀은 수정하지 않는다. 모순이나 빠진 점을 발견하면 고치지 말고 보고서의 "열린 결정"에 적는다.

## 진행 규칙

1. Phase 5B 범위만 구현한다. 튜터 질문 필터, RAG, 회고 검색, AI 인사이트(Phase 6), 일정 변경 화면, 목표 완료/보관 화면은 만들지 않는다. 튜터 화면의 안내문은 목업에 있으나 구현하지 않는다(Phase 6).
2. 끝나면 docs/phase5b_report.md 로 보고(테스트 출력, 완료한 Task 번호, 미완료, 사용자 조치 필요, 열린 결정)하고 멈춘다. 채팅에는 한 줄 요약만 남긴다. 다음 Phase 로 가지 않는다.
3. 비밀값을 코드, 로그, 채팅, 커밋에 남기지 않는다. 로그에 사용자 입력 원문, 회고, AI 응답 원문, 토큰을 남기지 않는다.
4. TASK.md 체크박스는 직접 검증한 항목만 체크한다. 브라우저에서 확인하지 못한 화면은 "미검증"이라고 적는다.
5. dev 모드(AUTH_MODE=dev, STORE_BACKEND=memory)로 구현한다. 실제 서버 확인은 빈 포트에 따로 띄우고 끝나면 종료한다.
6. DTO 를 바꾸면 backend/schemas.py, docs/erd_current.md, docs/phase1_design.md, 프론트 타입을 함께 갱신한다. 단 erd_current.md 에는 이미 start_date 와 복수 학습 규칙이 반영돼 있으니 구현과 어긋나는 부분만 보고서에 알린다.

## 승계 원칙 (그대로 지킨다)

- UID 는 토큰에서만. 소유 정보는 서버가 도출하고 검사한다. 개인 데이터 API 는 require_consented_uid, 오류는 ErrorResponse.
- 날짜와 주간 경계는 backend/clock.py, frontend/lib/week.ts 만 쓴다(Asia/Seoul). date.today(), 브라우저 로컬 날짜, toISOString 날짜 변환 금지.
- 쓰기 요청은 client_request_id 멱등. 계획은 확정할 때만 저장. 추천 요일은 마감일이 아니다. 진행률은 완료 과제 수 / 전체 과제 수. 수준 번호(order)는 계산·표시에 쓰지 않는다.

## 결정 사항 (PM 확정, 변경 금지)

- 일정 구간 = [goals.start_date, goals.target_date] (양 끝 포함). 두 활성 목표의 구간이 하루라도 겹치면 새 목표 생성을 거부한다.
- 비교 대상은 status="active" 인 목표뿐이다. completed, archived 는 비교하지 않는다.
- 거부는 409, 오류 코드 `GOAL_PERIOD_OVERLAP`, ErrorResponse 형식. 메시지에 겹치는 학습의 course 이름과 기간을 담되 사용자 입력 원문 전체를 로그에 남기지 않는다.
- 기존 학습의 일정 변경으로 생기는 겹침은 검사하지 않는다. 일정 변경 기능은 이 Phase 에 없다. 다만 PATCH /api/goals/{id} 가 target_date 를 바꿀 수 있다면 그 경로는 겹침 검사를 하지 않는다(사용자 결정)는 점을 코드 주석으로 남긴다.
- start_date 는 확정 시 plan_week_start(해당 주 월요일)로 한다. plan_week_start 가 없으면 clock 기준 이번 주 월요일.
- start_date 가 없는 기존 목표(이 Phase 이전 데이터)는 created_at 의 서비스 시간대 날짜를 start_date 로 간주하는 읽기용 보정 함수를 한 곳에 둔다. 저장 데이터는 일괄 변환하지 않는다.
- 새 목표 생성 경로는 두 개다(POST /api/plan/confirm, POST /api/goals). 둘 다 같은 검사 함수를 쓴다.

## Backend 작업

### B.1 겹침 검사
- 검사 함수 하나를 만들고 두 생성 경로에서 호출한다. 검증 순서: 기존 입력 검증을 모두 마친 뒤, 저장 직전에 검사한다(부분 저장 금지). plan/confirm 의 client_request_id 멱등 조회가 검사보다 먼저다(이미 만든 목표의 재시도는 겹침이 아니라 200 이다. 이전 Phase 에서 멱등 순서 결함이 있었다).
- GoalResponse, PlanConfirmResponse 에 start_date 추가. goals 에 start_date 저장.

### B.2 학습 전환
- 기존 PATCH /api/user/profile 로 active_goal_id 를 바꾼다. 서버는 그 목표가 본인 소유이고 status="active" 인지 검사한다(다른 UID 의 목표 id 는 404 또는 403 중 기존 관례를 따른다).
- GET /api/goals 가 start_date 를 포함해 반환하는지, 정렬이 최근 등록순인지 확인한다. 전환 드롭다운이 이 목록을 쓴다.

### B.3 대시보드 요약 확장
- 기존 GET /api/dashboard/summary 는 "최근 학습"(active_goal_id) 기준이다. 유지한다. 응답에 `goals_overview`(진행 중인 모든 학습의 id, course, start_date, target_date, 진행률, 완료/전체 과제 수) 목록을 추가한다. 최근 학습의 정의는 사용자가 마지막으로 전환했거나 새로 등록한 학습 = active_goal_id 다(별도 접속 시각 필드는 만들지 않는다).
- 모든 집계는 소유 UID 의 active 목표만. 목표별로 db.find 를 반복하지 말고 사용자 데이터를 한 번 읽어 묶는다(이전 Phase 의 N+1 지적 반영).

### B.4 종합 분석 API
- GET /api/analytics/overview 신설. 응답: 진행 중(active) 학습별 { goal_id, course, start_date, target_date, completed_task_count, total_task_count, progress_percentage, weekly_minutes_by_day(이번 주 월~일 7개, 분) }. 완료/보관된 학습은 포함하지 않는다. 읽기 전용이며 AI 를 호출하지 않는다. 주간 경계는 clock.py.
- 쿼리 주 이동(지난 주 보기)은 만들지 않는다. 필요하면 열린 결정에 적는다.

### B.5 백엔드 테스트
- 겹침: 같은 기간 거부, 하루만 겹쳐도 거부, 맞닿지 않는 기간 허용, completed/archived 와는 겹쳐도 허용, 두 생성 경로 모두, 멱등 재시도 200, 거부 시 아무것도 저장되지 않음, 다른 UID 목표와는 무관.
- 전환: 타 UID 목표 거부, 비활성 목표 거부.
- 대시보드/분석: 두 학습의 집계가 섞이지 않음, 완료 학습 제외, 타 UID 데이터 비포함, KST 자정 경계(clock 사용), 합계가 주간 기록과 일치.
- start_date 없는 기존 목표 보정.

## Frontend 작업

### B.6 학습 전환 도구
- 목업 `goal-switch`(작은 드롭다운, 라벨 "현재 학습")를 학습 경로 설정이 아닌 학습 과제 계획과 학습 실행 기록 화면 위쪽에 둔다(목업은 경로 설정 화면에도 있으나 그 화면은 새 학습을 만드는 흐름이라 현재 학습이 의미가 없다. 목업과 다른 이 판단을 보고서에 적는다). 대시보드, 튜터, 자료함에는 두지 않는다.
- 선택하면 PATCH /api/user/profile 로 active_goal_id 를 저장하고 화면 데이터를 다시 불러온다. 진행 중 타이머가 있을 때 전환해도 타이머는 그대로 유지되고, 실행 화면은 타이머의 과제가 속한 학습이 현재 학습과 다를 때 그 사실을 안내한다.
- 학습이 1개뿐이면 드롭다운 대신 이름만 보이게 하거나 숨긴다(목업은 2개 예시).

### B.7 대시보드 2영역
- 상단 통계 카드는 최근 학습 기준(라벨 "최근 학습 경로"), 그 아래 "종합 학습 현황 · 진행 중인 모든 학습" 카드는 goals_overview 로 표시. 학습이 1개뿐이어도 깨지지 않아야 하고, 0개일 때 기존 빈 상태를 유지한다.
- 새 학습 만들기에서 GOAL_PERIOD_OVERLAP 이 오면 겹치는 학습 이름과 기간을 보여 주고, 계획 입력(목표 날짜 등)을 지우지 않는다.

### B.8 종합 학습 분석 화면
- 메뉴 "종합 학습 분석" 추가. 목업 `page-analysis` 를 따른다: 진행 중인 학습별 일정, 진행률 바, 요일별 투입 시간 막대. 완료된 학습은 보이지 않는다. 읽기 전용. 차트 라이브러리를 새로 들이지 말고 CSS 막대로 구현한다(의존성 추가는 열린 결정에 적는다).
- 빈 상태, 로딩, 오류 상태를 둔다.

## 검증 기준 (검증팀이 직접 확인할 항목)

- pytest 전부 통과(보고서에 실제 건수), typecheck, npm test, npm run build.
- 같은 기간 두 번째 학습 확정 시 409 GOAL_PERIOD_OVERLAP, 맞닿지 않는 기간은 성공, 멱등 재시도 200.
- 학습 2개일 때 전환 후 계획·실행 화면이 해당 학습 데이터만 보이는지, 대시보드 종합 현황과 분석 화면의 숫자가 서로 일치하는지.
- 타이머 진행 중 전환, 학습 삭제 시 active_goal_id 정리(기존 동작 유지), 새로고침 후 선택 유지.
- 타 UID 격리, 동의 전 접근 차단.

## 보고서에 반드시 포함

- 목업과 다르게 구현한 점과 이유, 목업에 없어서 판단한 점.
- 브라우저로 직접 확인하지 못한 화면(미검증 목록).
- 열린 결정 목록.
