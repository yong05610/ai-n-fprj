# Phase 5B 보고 — 복수 학습 운용 (MULTI)

**기준:** docs/phase5b_dev_prompt.md, docs/multi_goal_design.md
**상태:** 2026-10-22 구현 완료, 재검증 대기. Phase 6 은 시작하지 않았다.

## 1. 완료한 Task

| Task | 상태 | 확인 방법 |
|---|---|---|
| B.1 겹침 검사, start_date | 완료 | pytest + 실제 서버 HTTP |
| B.2 학습 전환 | 완료 | pytest + 실제 서버 HTTP |
| B.3 대시보드 goals_overview | 완료 | pytest + 실제 서버 HTTP |
| B.4 GET /api/analytics/overview | 완료 | pytest + 실제 서버 HTTP |
| B.5 백엔드 테스트 | 완료 | 신규 40건 |
| B.6 학습 전환 드롭다운 | 구현됨, **화면 미검증** | typecheck, build 만 |
| B.7 대시보드 2영역, 겹침 오류 안내 | 구현됨, **화면 미검증** | typecheck, build 만 |
| B.8 종합 학습 분석 화면 | 구현됨, **화면 미검증** | typecheck, build 만 |

TASK.md 는 B.1~B.5 만 체크했다. B.6~B.8 은 브라우저로 확인하지 못해 체크하지 않았다.

## 2. 테스트 결과

- backend `python -m pytest -q`: **225 passed** (기존 185 + 신규 40).
- frontend `npm run typecheck` 통과, `npm test` 6건 통과, `npm run build` 통과.
- 실제 서버 HTTP (빈 포트 8123, `AUTH_MODE=dev`, `STORE_BACKEND=memory`, 확인 후 종료): 첫 학습 확정 201 + `start_date`=이번 주 월요일, 같은 기간 두 번째 학습 409 `GOAL_PERIOD_OVERLAP`(메시지에 과정명과 기간 포함), 같은 `client_request_id` 재시도 200, 맞닿지 않는 기간 201, 새 등록이 `active_goal_id` 가 됨, `PATCH /api/user/profile` 전환 200, 대시보드 `goals_overview` 와 분석 API 응답 확인. 실제 AI 호출은 이 Phase 에 없다.

## 3. 변경 파일

**Backend**
- `backend/schemas.py`: `GoalResponse.start_date`, `GoalOverviewItem`, `DashboardSummaryResponse.goals_overview`, `AnalyticsGoalItem`, `AnalyticsOverviewResponse` 추가.
- `backend/main.py`:
  - 겹침 검사 `_check_goal_period_overlap` 한 개를 `POST /api/plan/confirm` 과 `POST /api/goals` 가 공유한다. 입력 검증을 모두 마친 뒤 저장 직전에 호출한다. plan/confirm 의 멱등 조회는 검사보다 먼저다.
  - `_goal_start_date` / `_goal_out`: start_date 가 없는 기존 목표는 `created_at` 의 Asia/Seoul 날짜로 읽기용 보정(저장 데이터는 변환하지 않음). 목표를 돌려주는 모든 경로(목록, 상세, 생성, 수정, plan/confirm)가 거친다.
  - 새 목표 등록(두 경로)은 항상 `active_goal_id` 로 설정한다(최근 학습 = 마지막 등록 또는 전환). 이전에는 비어 있을 때만 설정했다.
  - `PATCH /api/user/profile`: 본인 소유(타 UID 는 기존 관례대로 403, 없는 id 는 404)이고 `status=active` 인 목표만 허용. 아니면 400.
  - `GET /api/dashboard/summary`: 사용자의 과제와 기록을 한 번만 읽어 목표별로 묶는다(목표별 `db.find` 반복 없음). `goals_overview` 와 `GET /api/analytics/overview` 는 같은 헬퍼(`_active_goals_sorted`, `_goal_progress`)를 써서 숫자가 어긋나지 않는다.
  - `GET /api/study-logs` 에 선택 쿼리 `goal_id` 추가(아래 4번 참고).
  - `PATCH /api/goals/{id}` 에 "일정 변경은 겹침 검사를 하지 않는다(사용자 결정)"는 코드 주석을 남겼다.
- `backend/tests/test_phase5b_multi.py`: 신규 40건. `backend/tests/test_phase4_plan.py`: 두 기존 테스트가 같은 기간의 목표를 둘 만들던 것을 겹치지 않는 기간으로 수정(규칙 변경에 따른 정당한 수정).

**Frontend**
- `components/GoalSwitch.tsx`(신규), `components/AnalysisScreen.tsx`(신규), `components/ExecutionScreen.tsx`, `components/Dashboard.tsx`, `components/LearningPathWizard.tsx`, `app/page.tsx`(메뉴 "종합 학습 분석"), `app/globals.css`.

**문서**: `docs/phase1_design.md`(API 표), `TASK.md`. `docs/erd_current.md` 는 이미 start_date 와 복수 학습 규칙이 있어 수정하지 않았다. 구현과 어긋나는 점은 없고, 48행의 "구현 전" 표기만 이제 낡았다(PM 소유라 두었다).

## 4. 목업과 다르게 구현한 점, 목업에 없어서 판단한 점

1. **학습 전환 드롭다운은 실행 화면에만 있다.** 프론트에는 "학습 과제 계획" 화면(mockup `page-wbs`, 기존 목표의 주간 계획 보기)이 아직 없다. 계획 단계는 새 학습을 만드는 마법사뿐이다. 마법사에는 지시서대로 두지 않았다. 계획 화면은 7.1(Phase 7)에서 목업과 대조할 때 같은 `GoalSwitch` 를 붙이면 된다.
2. **`GET /api/study-logs` 에 `goal_id` 필터를 추가했다(지시서에 없음).** 실행 화면의 상단 지표(학습 시간, 기록 수)가 사용자의 모든 학습 기록을 합산하고 있어서, 학습 2개일 때 "현재 학습"의 숫자가 섞인다. 기존 호출은 그대로 동작하는 선택 파라미터다.
3. 학습이 1개면 드롭다운 대신 이름만 보인다(지시서 권장안). 진행 중인 학습이 없으면 스위치를 숨긴다.
4. 타이머가 현재 학습이 아닌 학습의 과제에서 진행 중이면 실행 화면 위에 안내 문구를 보여 준다(어느 학습인지 과정명 포함). 전환해도 타이머는 건드리지 않는다.
5. 대시보드의 "최근 학습 경로" 라벨은 상단 카드 안에 작은 소제목으로 넣었다. 목업의 정확한 배치와 다를 수 있다.
6. 분석 화면의 막대 높이는 해당 학습의 이번 주 최대값 기준 비율(최소 6%)이다. 목업의 고정 픽셀 예시와 다르다.
7. 목록 정렬: `created_at` 이 초 단위라 같은 초에 등록된 목표는 일정이 늦은 쪽이 먼저 오도록 보조 키를 뒀다(최근 등록순 유지).

## 5. 미검증 항목 (브라우저에서 확인하지 못함)

- 학습 전환 드롭다운 동작, 전환 후 실행 화면의 과제·기록 갱신, 새로고침 뒤 선택 유지(서버 저장이라 API 로는 확인함).
- 대시보드 "최근 학습 경로"와 "종합 학습 현황" 레이아웃, 학습 0개·1개·2개 표시.
- 겹침 오류 안내(마법사에서 입력 유지, 오류 문구).
- 종합 학습 분석 화면(진행률 바, 요일별 막대, 빈/로딩/오류 상태).
- 진행 중 타이머 상태에서 전환했을 때의 안내 문구.
- Firebase 실연동(여전히 미검증).

사용자가 눌러 볼 시나리오: (1) 학습 A 를 만든 뒤 기간이 겹치는 B 확정 → 안내와 입력 유지 확인, (2) 겹치지 않게 B 를 만들고 실행 화면에서 드롭다운 전환, (3) A 에서 타이머를 켠 채 B 로 전환 → 안내 문구, (4) 대시보드 종합 현황과 분석 화면의 숫자 일치, (5) 새로고침 뒤 선택한 학습 유지.

## 6. 열린 결정 (PM 확인 요청)

1. **계획 화면 부재:** 위 4-1. 7.1 에서 계획 보기 화면을 만들 때 전환 도구를 붙이는 것으로 두어도 되는지.
2. **`/api/goals` 의 start_date 보정을 읽기마다 계산한다.** 기존 데이터를 일괄 변환하지 않는다는 지시대로다. Firestore 연동 후 쿼리 정렬이 필요하면 그때 재검토.
3. **차트 라이브러리는 추가하지 않았다**(CSS 막대, 의존성 변경 없음).
4. 쿼리 주 이동(지난 주 보기)은 만들지 않았다. 필요하면 후속 후보.
5. 겹침 검사가 시작일을 "확정 시 plan_week_start(월요일)"로 잡으므로, 한 주 안에서 끝나는 학습 둘은 같은 주 월요일부터 시작해 겹친다(예: 같은 주 안에 두 번째 학습 불가). 의도한 규칙인지 확인 필요.
6. POST /api/goals 는 요청에 `client_request_id` 가 없어 멱등 재시도 대상이 아니다(plan/confirm 만 해당). 계약 변경이라 손대지 않았다.
7. 작업 폴더의 `frontend/next-env.d.ts` 는 dev 서버가 자동으로 바꾼 것으로 보여(이 Phase 의 변경 아님) 커밋에 포함하지 않았다. 현재 포트 3000(프론트)과 8001(백엔드)에 다른 세션의 서버가 떠 있었고 건드리지 않았다.

## 7. Git

커밋과 push 는 이 보고 후 수행한다(테스트 통과, 비밀값 없음, 의도한 파일만).

---

보고 후 멈추고 검증팀 검증을 기다립니다. Phase 6 은 시작하지 않았습니다.
