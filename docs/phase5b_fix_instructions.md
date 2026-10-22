# Phase 5B 검증 결과와 수정 지시 (검증팀 겸 PM, 2026-10-22)

대상: docs/phase5b_report.md, 커밋 b0d2de9. 기준: docs/phase5b_dev_prompt.md.

## 1. 직접 확인한 것 (dev 모드, 메모리 저장소)

- backend pytest 225 passed(보고와 일치), frontend typecheck 통과, npm test 6건 통과. `npm run build` 는 이 세션에서 다시 돌리지 않았다.
- 빈 포트에 실제 서버를 띄워 재현(확인 후 종료):
  - 첫 학습 확정 201, start_date = 계획 주 월요일.
  - 겹치는 기간의 두 번째 학습 409 GOAL_PERIOD_OVERLAP, 거부 뒤 목표 수 1(부분 저장 없음).
  - 같은 client_request_id 재시도 200.
  - 첫 학습 종료일 다음 날 시작하는 학습 201(맞닿는 경우 허용), 종료일 이내 시작은 409.
  - 새로 등록한 학습이 active_goal_id 가 됨.
  - 전환: 본인 active 목표 200, 타 UID 목표 403, 없는 id 404, completed 목표 400.
  - 분석 API 와 대시보드 goals_overview 에서 completed 학습 제외, 두 값 일치. 타 UID 는 빈 목록.
- 코드 확인: 겹침 검사는 두 생성 경로(plan/confirm, POST /api/goals)가 한 함수를 쓰고 저장 직전에 호출한다. 멱등 조회가 검사보다 앞이다.

## 2. 수정 지시

### P5B-1 (필수) 현재 학습(active_goal_id)을 삭제하면 다른 진행 중 학습이 있어도 "학습 없음" 상태가 된다
- 재현: 학습 A, C 를 차례로 확정(active_goal_id=C) → DELETE /api/goals/{C} 200 → GET /api/user/profile 의 active_goal_id=null, GET /api/dashboard/summary 의 active_goal_title="" 인데 goals_overview 에는 A 가 있다. 대시보드 상단 카드와 실행 화면은 비고, 종합 현황만 A 를 보여 불일치한다. 전환 드롭다운은 "학습을 선택하세요" 상태가 된다.
- 요구: 현재 학습이 삭제되면 남은 status=active 목표 중 가장 최근 등록(또는 정렬 규칙상 첫 번째)으로 active_goal_id 를 옮기고, 없을 때만 null. 현재 학습이 completed/archived 로 바뀌는 경로(PATCH /api/goals/{id})가 있다면 같은 규칙. 정렬 기준은 목록 정렬과 동일하게(보조 키 포함) 한다.
- 테스트: 위 재현 시나리오, 남은 활성 학습이 없을 때 null, 다른 학습을 삭제해도 active_goal_id 유지, 타 UID 영향 없음.

### P5B-2 (참고, 코드 변경 없음) 보고서 §6 열린 결정에 대한 PM 답
1. 계획 화면 부재: 인정한다. 지시서의 "계획·실행 화면" 가정이 틀렸다(PM 오류). 목업의 `page-wbs`(주간 계획 보기)는 미구현으로 배지를 바꿨다. 전환 도구는 7.1 에서 그 화면을 만들 때 붙인다. 마법사에는 두지 않는 판단이 맞다.
2. start_date 보정을 읽을 때 계산: 승인.
3. 차트 라이브러리 없음: 승인.
4. 지난 주 보기: 만들지 않는다(후속 후보로 docs/post_mvp_backlog.md 에 기록할 것).
5. 같은 주 월요일 시작으로 겹침: 의도한 규칙이다. 단 사용자에게 "주 단위로 일정이 잡힌다"는 점을 겹침 오류 문구가 알려 주는지는 화면 확인에서 본다.
6. POST /api/goals 에 client_request_id 없음: MVP 화면은 plan/confirm 만 쓰므로 수용한다. 후속 후보로 기록.
7. next-env.d.ts 미포함: 맞다.

## 3. 미검증 (사용자 화면 확인 필요)

보고서 §5 의 시나리오 (1)~(5), 그리고 분석 화면, 대시보드 2영역, 학습 0/1/2개 표시. 사용자가 눌러 확인한 뒤 결과를 알려 주면 결함이 있을 때 이 문서에 이어서 적는다.

## 4. 판정

P5B-1 수정 후 재검증하면 백엔드는 승인 가능하다(dev 모드). 프론트(B.6~B.8)는 화면 확인 전까지 승인하지 않는다. 수정 후 docs/phase5b_fix_report.md 로 보고하고 멈춘다. Phase 6 은 시작하지 않는다.
