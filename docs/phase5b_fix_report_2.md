# Phase 5B 수정 보고 2 (F1~F5, 화면 확인 피드백)

**기준:** docs/phase5b_fix_instructions_2.md (대상 커밋 83eeac2)
**상태:** 2026-10-22 수정 완료, 재검증 대기. Phase 6 은 시작하지 않았다.
**환경:** backend/.env 가 firebase 모드라서 서버는 `AUTH_MODE=dev STORE_BACKEND=memory` 를 명령줄로 덮어써 빈 포트(8123)에 띄웠고 확인 후 종료했다. `.env`, `.env.local` 은 수정하지 않았다. 테스트는 이 폴더의 `backend/.venv` 의 파이썬으로 돌렸다.

## 1. 수정 항목과 변경 파일

| 항목 | 내용 | 파일 |
|---|---|---|
| F1 (필수) | 학습 시작일을 사용자가 고른다. `PlanGenerateRequest`, `PlanConfirmRequest` 에 `start_date`(필수) 추가. 서버가 `clock.week_monday(start_date)` 로 계획 주간(`plan_week_start`)을 도출한다. 요청의 `plan_week_start` 는 선택이며 주어지면 그 월요일과 다르면 400. `goals.start_date` = 사용자가 고른 날짜, 겹침 검사는 [start_date, target_date]. | `backend/schemas.py`, `backend/main.py`(`_resolve_plan_period`), `frontend/components/LearningPathWizard.tsx`, `frontend/lib/wizardDates.ts` |
| F2 (필수) | 겹치는 학습을 전부 알린다. 409 `GOAL_PERIOD_OVERLAP`, `details.overlaps=[{goal_id, course, start_date, target_date}…]`(일정 빠른 순), 기존 단일 필드는 첫 항목으로 유지. 메시지: "이 기간에 이미 N개의 학습이 있습니다: …". 화면은 시작일·완료일 입력칸 바로 아래에 오류를 보이고, 날짜를 바꾸면 오류를 지워 다시 저장할 수 있게 하며, 입력칸 아래에 "진행 중인 학습과 일정이 겹치면 새 학습을 만들 수 없어요." 한 줄을 둔다. | `backend/main.py`(`_check_goal_period_overlap`), `LearningPathWizard.tsx` |
| F3 (필수) | 새로고침과 학습 전환 뒤에도 진행 중 타이머가 보인다. 로드 후 타이머가 현재 학습의 것이면 그 과제를 자동 선택(사용자가 이미 고른 과제는 유지). 상태 계산은 순수 함수(`taskToSelectForTimer`, `timerLocation`). 같은 학습의 다른 과제에서 타이머가 돌면 "진행 중인 과제로 이동", 다른 학습이면 "그 학습으로 돌아가기" 버튼. 시작이 `TIMER_ALREADY_RUNNING` 으로 거부되면 타이머 상태를 다시 읽고 "이미 진행 중인 타이머가 있어요…" 안내와 이동 버튼을 보인다. | `frontend/lib/timerSelection.ts`, `frontend/components/ExecutionScreen.tsx` |
| F4 개정 (필수) | 마법사의 자유 입력(분야, 학습 목표, 과정명, 수준 이름, 과업 제목)에 `autoComplete="off"`. 브라우저 입력 기록 말풍선이 뜨지 않게 한다. 앞의 "React 상태 잔존" 가설은 지시대로 폐기. | `LearningPathWizard.tsx` |
| F5 (필수) | 흐름: 분야 → [대표 직무·목표 예시 보기] → 직무 chip(참고용, 누르면 학습 목표 칸에 채워짐) → 학습 목표 → [AI 세부 과정·수준 추천] → 과정 → 수준 → 시간·시작일·완료일 → 계획 생성. 신규 `POST /api/path/ideas`(입력 `field` 만, 응답 `suggested_roles` 3~5개, 항목 40자 이하, 공백·중복 불가, 위반은 거부 후 재시도, 버튼을 눌렀을 때만 호출). 기존 과정 선택 뒤의 직무 chip 은 제거했다. `/api/path/recommend` 는 코드·프롬프트 변경 없이 그대로다(roles 는 호환용으로 계속 올 수 있고 화면은 쓰지 않는다). | `backend/schemas.py`(`RoleIdeasRequest/Response`), `backend/ai_schemas.py`(`AIRoleIdeas`), `backend/prompts.py`(`ROLE_IDEAS_SYSTEM_PROMPT`), `backend/main.py`(`suggest_role_ideas`), `LearningPathWizard.tsx` |
| F6 (취소) 확인 | 라벨 변경 없음. 읽기만 했다: `PATH_RECOMMEND_SYSTEM_PROMPT` 는 수준 이름을 "번호나 '1단계' 같은 표현이 아니라 분야에 맞는 서술형 이름"으로 지으라고 이미 지시한다(예: 입문자, 실무 개발자, 시스템 설계자). 프롬프트는 바꾸지 않았다. | — |

계약 문서: `docs/phase1_design.md` API 표(`/api/path/ideas` 추가, plan/generate 의 start_date, goals 행의 `details.overlaps`). `docs/erd_current.md` 는 PM 이 이미 수정한 start_date 설명과 구현이 일치해 건드리지 않았다.

## 2. 결정한 사항 (지시서가 개발팀 선택으로 남긴 것)

- **target_date = start_date 허용.** 기존 목표일 규칙(오늘 이후, 오늘 포함)을 따라 같은 날 하루짜리 학습을 허용한다. target < start 는 400(`details.field=target_date`).
- **selected_role 처리:** 직무 chip 을 누르면 `selected_role` 과 학습 목표 칸이 같은 값이 된다. 사용자가 목표 텍스트를 고치면 `selected_role` 은 null 로 바뀐다(목표와 어긋난 직무를 보내지 않기 위해). chip 을 한 번 더 누르면 선택 해제(목표 텍스트는 그대로). 분야를 바꾸면 예시와 선택 직무를 비운다(이전 분야의 예시가 남지 않게).
- **`POST /api/goals` 는 start_date 를 받지 않는다.** 지시 범위(PlanGenerate/PlanConfirm)에 없어 이번 주 월요일을 그대로 쓴다. 화면은 이 경로를 쓰지 않는다.
- **복원된 임시 저장(sessionStorage)** 의 시작일이 이미 지났으면 오늘로 되돌린다(저장 단계에서 갑자기 400 이 나지 않게).
- 날짜를 바꾸면 기존 동작대로 계획 초안이 "최신 상태 아님"이 되어 "계획 다시 만들기"가 필요하다(시작일이 계획 주간을 바꾸므로 의도한 동작).

## 3. 테스트 결과

- backend (`backend/.venv` 파이썬): **258 passed** (직전 232 + 신규 26).
  - 신규 `backend/tests/test_phase5b_fix2.py`: 시작일 선택 시나리오(멀리 있는 기존 학습과 겹침 재현 → 이전/이후 기간은 201, 걸치면 409), 시작일이 월요일이 아니어도 201 이고 plan_week_start 는 그 주 월요일, 과거 시작일 400, 타 UID 격리, 다중 겹침(둘 다 `overlaps` 에 포함, 저장 없음, 겹치지 않는 학습은 목록에서 제외), `/api/path/ideas`(정상, 5개, 규칙 위반 6종 재시도 후 502 와 호출 횟수, 위반 뒤 정상 응답, 타임아웃 504, 공백 422, 미인증 401·미동의 403, 모델에 field 만 전달, recommend 가 roles 없이도 동작).
  - 기존 테스트 갱신: 요청에 `start_date` 를 넣고 "오늘"을 2026-10-21 로 고정(시작일이 오늘 이후여야 하므로), 월요일 강제 테스트를 "plan_week_start 불일치", "과거 시작일", "target < start" 로 대체, `test_phase5b_multi.py` 의 일정 값 갱신.
- frontend: `npm run typecheck` 통과, `npm test` **16건 통과**(직전 6 + 신규 10: 시작일 규칙 5, 타이머 선택 규칙 5), `npm run build` 통과.

## 4. 실제 서버 HTTP 확인 (빈 포트 8123, dev 모드)

- 멀리 있는 기존 학습(오늘+100일 ~ +106일) 확정 201, `start_date` 그대로, 계획 주간은 그 주 월요일.
- 그 기간을 통째로 포함하는 새 학습(오늘 ~ +200일): **409** `GOAL_PERIOD_OVERLAP`. 바로 앞(오늘 ~ +99일)과 바로 뒤(+107일 ~)는 둘 다 **201**.
- 기존 학습 둘을 한 번에 가로지르는 새 학습: 409, `overlaps` 에 둘 다.
- 과거 시작일: plan/confirm, plan/generate 모두 400. 다른 UID 는 같은 기간도 201(격리 유지).
- **실제 OpenAI 호출 1회(`POST /api/path/ideas`, field="Python 개발")**: 200, 5개 반환, 각 항목 길이 모두 40자 이하(콘솔 인코딩 때문에 한글은 깨져 보였고 개수·길이만 확인). 키 값은 출력하지 않았고, 서버 로그에 키 형태 문자열이 없음을 확인했다. 확인 후 서버 종료.

## 5. 미검증 (사용자 화면 확인 필요)

- 마법사 새 흐름 전체(분야 → 예시 → 목표 → 과정 → 수준 → 날짜), 예시 chip 이 목표 칸을 채우는 동작, 날짜 입력 UI, 겹침 오류 위치와 "날짜를 바꾸면 오류가 사라지는" 동작.
- 브라우저 자동완성 말풍선이 실제로 사라졌는지(`autoComplete="off"` 는 브라우저가 무시하는 경우도 있다).
- 타이머: 새로고침(F5) 후 진행 시간·"학습 종료" 버튼이 보이는지, 다른 학습으로 전환했다 돌아왔을 때, "그 학습으로 돌아가기"/"진행 중인 과제로 이동" 버튼. 상태 계산 함수만 단위 테스트했다.
- Firebase 실연동(미검증, 이번 수정과 무관).

사용자가 눌러 볼 시나리오: (1) 학습 A 를 만든 뒤 마법사에서 시작일을 A 의 종료일 다음 날로 골라 저장 → 성공, (2) A 와 겹치는 날짜로 저장 → 오류가 날짜 입력칸 아래에 보이고 날짜를 바꾸면 사라짐, (3) 타이머를 켠 뒤 F5, (4) 타이머를 켠 채 다른 학습으로 전환 → 안내와 돌아가기 버튼 → 돌아가면 진행 시간이 보임, (5) 분야 입력 후 "대표 직무·목표 예시 보기" → chip 을 눌러 목표 칸 채우기.

## 6. 열린 결정

1. **첫 주 과제량:** AI 프롬프트에 start_date 를 알려 첫 주(시작일이 주 중간인 경우) 과제량을 배분하는 것은 지시대로 이번 범위가 아니다. 지금은 시작일이 수요일이어도 첫 주에 주당 시간 전체의 과제가 배정될 수 있다.
2. `docs/phase1_design.md` 50행의 사용자 여정 문장(분야 입력 → recommend → …)은 새 흐름(예시 → 목표 → recommend)과 다르다. 설계 서술이라 PM 이 고치도록 두었다.
3. `/api/path/recommend` 의 `suggested_roles` 와 프롬프트의 직무 요청은 남아 있어 출력 토큰을 조금 더 쓴다. 비용을 줄이려면 프롬프트에서 직무 요청을 빼는 변경이 필요한데, 실제 모델로 다시 확인해야 해서 이번에는 하지 않았다. 결정이 필요하다.
4. 같은 학습을 반복해서 만들 때 쓸 `POST /api/goals` 의 start_date 입력은 지금 없다(후속 후보로 이미 백로그에 기록됨).

---

보고 후 멈추고 검증팀 재검증을 기다립니다. Phase 6 은 시작하지 않았습니다.
