# CR-014 보고서 — 학습 실행 화면의 주간 목표 계산과 과제 표시

작성: 개발팀, 2026-11-10. 지시서: `docs/cr014_dev_prompt.md`. E-1·E-2·E-3 만 했다(E-4~E-7, DB 스키마 변경, push 없음).

## 1. 무엇을 했나
**E-1 주간 목표 분모**: 분모를 활성 학습의 `weekly_hours × 60` 으로 바꿨다(주 7시간 → 420분, 대시보드 `weekly_target_minutes` 와 같은 값). `주 목표 N분`, `주간 목표 달성 %`, `N분 / M분` 이 모두 이 값을 쓰고 100% 상한은 유지. `weekly_hours` 는 `GET /api/goals` 에 이미 있어 프론트 `GoalOption` 에 선택 필드로만 추가(계약 변경 아님).
- `전체 기간`: % 를 계산하지 않고 큰 글자 `–`, 아래 문구 **`이번 주 보기에서 확인`**, 학습시간 카드 문구는 `전체 기간`.
- `weekly_hours` 없음·0 이하: `–` + 문구 **`주 목표를 읽지 못했어요`**(0 나누기·NaN 없음).

**E-2 과제 설명**: 과제 묶음 제목 아래에 `description` 을 12px 보조 글자(`small muted task-desc`)로 표시, 2줄에서 줄임(`-webkit-line-clamp: 2`, 펼치기 없음). 빈 문자열·공백이면 줄을 만들지 않는다.

**E-3 이번 주 과제만 표시**: `GET /api/tasks` 응답에 **선택 필드 `in_current_week`(bool)** 를 추가했다. 서버가 대시보드와 같은 `schedule.tasks_in_week` 규칙으로 계산한다(그 학습의 **전체** 과제 타임라인으로 판단하므로 `goal_id`·`plan_week_start` 필터를 써도 같다. 오늘은 `clock.today()`, 월~일, Asia/Seoul). 프론트는 타임라인을 계산하지 않는다.
- `이번 주` 보기: `in_current_week` 가 true 인 과제 + 이번 주 기록이 있는 과제. `전체 기간`: 전체.
- 보일 과제가 0개면 **`이번 주에 배치된 과제가 없어요. 전체 기간에서 확인하세요`**.
- 필드가 없는 응답(구 서버)이면 과제를 숨기지 않는다.

## 2. 바꾼 파일
| 파일 | 내용 |
|---|---|
| `backend/schemas.py` | `TaskResponse.in_current_week: Optional[bool] = None` |
| `backend/main.py` | `list_tasks` 가 `in_current_week` 를 채움, `_this_week_task_ids()` 추가 |
| `docs/phase1_design.md` | `GET /api/tasks` 행에 `in_current_week` 설명(계약 변경 규칙). `docs/erd_current.md` 는 저장 필드가 아니라(파생값) 바꾸지 않음 |
| `frontend/lib/executionView.ts` (신규) | `weeklyTargetMinutes`, `goalStat`, `visibleTasks`, `taskDescription` 과 문구 상수 |
| `frontend/components/ExecutionScreen.tsx` | 분모·카드·과제 목록·설명·빈 상태 연결, 과제 메타 `누적` → `실제`(목업과 맞춤) |
| `frontend/components/GoalSwitch.tsx` | `GoalOption.weekly_hours?` |
| `frontend/app/globals.css` | `.task-record-head .task-desc` |
| `backend/tests/test_cr014_tasks_in_week.py` (신규, 8건), `frontend/lib/executionView.test.ts` (신규, 9건) | 시험 |

## 3. 목업 대조 (`mockup/index.html` `page-execution`, `renderActivity()`)
| 영역 | 목업 | 구현 | 일치 |
|---|---|---|---|
| 통계 카드 4개 순서·문구 | 이번 주 학습시간(주 목표 420분) → 학습 기록 → 진행 중인 과제(전체 학습 과제 N개) → 주간 목표 달성(44%, 185분 / 420분) | 같은 순서. 제목, 큰 숫자, 1·3·4번째 보조 문구 일치(주 7시간 → `주 목표 420분`, `42분 / 420분`). 2번째 카드 보조 문구는 목업 `여러 기록을 과제별로 관리`, 구현은 기간에 따라 `이번 주 기록`/`전체 기간 기록`(기존 그대로, 변경 안 함). 전체 기간 보기의 `–`·안내 문구는 목업에 없는 신규 상태 | 대체로 일치 (2번째 보조 문구 차이, PM 판단 요청) |
| 과제 묶음 제목 → 설명 → 계획/실제/기록 메타 순서 | h3 → `small muted task-desc` → `계획 N분 · 실제 M분 · 기록 K건` | 브라우저에서 자식 순서 H3 → P.task-desc → DIV.task-record-meta 확인, 메타 문구 `실제` 로 맞춤 | 일치 |
| 기간 선택 위치 | `과제별 학습 기록` 카드 머리 오른쪽 | 그대로(변경 없음) | 일치 |
참고: 목업에는 `.task-desc` CSS 가 없어 값(12px, 2줄 줄임)은 지시서를 따랐다. 목업의 `과제 완료 처리` 버튼은 E-5(하지 않음).

## 4. 시험
**pytest 1378건 통과(이전 1370 + 8), npm test 246건 통과(이전 237 + 9), `npm run typecheck`, `npm run build` 통과.** 기존 시험의 기대값은 바꾸지 않았다.
- 백엔드 8건: 첫 주 표시, 두 주에 걸친 과제가 양쪽 주에서 true, 배치가 없는 주, 필터를 써도 전체 타임라인 기준, **대시보드 `today_tasks` 와 4개 주 모두 같은 과제**, 학습별 타임라인 분리, 타 UID 과제 미노출, 기존 필드 유지·`PATCH` 응답은 null(선택 필드).
- 프론트 9건: 7시간 → 420, 알 수 없는 값 → null, %·상한 100, 전체 기간 % 미표시, `weekly_hours` 없음(NaN 없음), 설명·빈 설명, 이번 주 필터(배치/기록만 있음/0개), 구 서버(필드 없음), 화면 연결·CSS 값.

## 5. 실제 브라우저 확인 (dev 모드, Chrome 헤드리스, 1280px·360px, 22개 항목 통과)
- 주 7시간, 오늘 42분 기록: `주 목표 420분`, `42분 / 420분`, `10 %`. 전체 기간: `–` + `이번 주 보기에서 확인`, 과제 3개 전부.
- 설명: 있는 과제 2개에만 줄이 생기고(빈 설명 1개는 없음), 긴 설명은 12px 에 2줄에서 잘림. 가로 스크롤 없음, 페이지 오류 0.
- 이번 주 필터(주 1시간, 60분 과제 4개): 이번 주에는 A 만 보임 → 과제 B 에 이번 주 기록을 넣으면 A,B → 전체 기간은 A,B,C,D. 시작일이 다음 주인 학습은 안내 문구가 보임.

## 6. 미검증·참고
- 실제 AI 가 만든 계획·실제 휴대폰 확인은 하지 않았다. Firestore(STORE_BACKEND=firestore)에서의 `GET /api/tasks` 응답 시간은 확인하지 않았다(학습별로 과제를 한 번 더 읽는다. 사용자당 학습 수가 작아 영향은 작다고 보지만 미측정).
- `PATCH`·`POST /api/tasks` 응답의 `in_current_week` 는 null(목록 조회에서만 채움).
- 확인용 `npm run build` 는 이미 떠 있던 포트 3000 개발 서버와 `.next` 를 공유한다. 화면이 이상하면 그 서버를 다시 시작.
- 이 작업과 무관한 파일은 커밋하지 않았다: `docs/프롬프트와 응답사례연구.md`, `frontend/AGENTS.md`, `변경관리내역서.hwp/.pdf`.
