# Phase 5D(학습 과제 계획 화면) 검증 결과 (PM, 2026-10-23)

**대상:** 커밋 8024978, 지시서 docs/phase5d_dev_prompt.md, 개발팀 보고 docs/phase5d_report.md
**판정:** 백엔드·API·계약 변경은 승인(dev 모드). 화면 동작은 개발팀 보고만 있어 PM 미검증(사용자 확인 대기). Firebase 실연동 미검증.

## 1. 직접 확인한 것
- backend `pytest` **337 passed**(직전 319 + 신규 18), frontend `typecheck` 통과, `npm test` **54 passed**(직전 34 + 신규 20), `npm run build` 통과.
- 코드 읽기: `main.py` 의 확정 시 advice 저장, `GET /api/goals/{id}/references`(소유권은 토큰 UID, `match_references` 재사용), `schemas.py`(advice 둘 다/둘 다 없음 검증, 길이 200/4000, 공백 거부, GoalResponse 에 Optional 필드, `source_name` 추가). 지시서와 일치. 날짜 계산은 `lib/week.ts` 안에서만 하고 UTC 기준 연·월·일 산술이며 브라우저 로컬 날짜를 쓰지 않음(컴포넌트·weekPlan·latestWins 에 toISOString, new Date() 없음).
- 실제 서버(빈 포트 8214, dev + memory, `.env` 미수정, 종료 확인):

| 확인 | 결과 |
|---|---|
| advice 와 함께 확정 | 201, 응답 goal 에 advice_title/content |
| advice 제목만 | 422 |
| 공백만 | 422 |
| 제목 201자 | 422 |
| advice 없이 확정(기존 형태) | 201, advice null |
| 같은 client_request_id 재요청(다른 advice) | 200, 처음 저장한 advice 유지 |
| `GET /api/goals/{id}/references` (Python 개발) | 200, 자료 3건, source_name "Python 공식 문서" |
| 자료 없는 분야(요리) | 200, 빈 목록 + 안내문(근거 있는 것처럼 표시하지 않음) |
| 타 UID 조회 / 없는 id | 403 / 404 |
| PATCH 추천 요일 sat / 잘못된 값 | 변경됨 / 422 |
| GET /api/goals | advice 있는 목표와 없는 목표가 구분되어 내려옴 |
| 같은 기간 세 번째 학습 | 409 (R1 규칙 정상) |

## 2. 미검증
- 화면 동작 전체(주 이동, 요일 즉시 저장, 연속 변경 시 마지막 값, 저장 실패 후 재시도, 학습 전환, 모바일 폭): 개발팀 Chrome 확인 보고만 있고 PM 이 보지 못했다. 마지막 값 우선 로직의 단위 테스트(latestWins)가 통과한 것은 확인.
- 목업 page-wbs 와의 나란히 비교(개발팀 대조표만 있음), AI 로 위저드를 끝까지 돌린 확정, Firebase 실연동.

## 3. 열린 결정 처리
1. 참고자료 없음 안내문 끝의 "아래 계획은 등록 자료 없이 AI 가 생성한 일반 계획입니다.": 이 화면에서는 어색하지만 동작에는 문제가 없어 이번에는 그대로 둔다. docs/post_mvp_backlog.md 에 올렸다(서버 문구를 plan/generate 용과 화면용으로 나누는 작업).
2. `source_name` 추가: 승인(지시서의 "{출처} · {분류}" 표시에 필요한 계약 변경). erd_current.md 와 phase1_design.md 갱신도 diff 에서 확인.
3. 빈 주 건너뛰기 이동과 "3주 뒤" 표현: 승인.
4. 저장 중 화면 이탈 시 결과 미표시: 승인(MVP 범위).
5. 실패 후 같은 과제를 다시 바꾸면 이전 실패가 새 값으로 대체됨: 승인.

## 4. 사용자가 직접 눌러 볼 항목
1. 사이드바 "학습 과제 계획" → 이번 주 과제와 진행 바, 우측 AI 학습 조언·참고자료가 보이는가(목업 page-wbs 와 비교).
2. 추천 요일을 바꾸고 새로고침 → 값이 유지되는가. 같은 과제를 빠르게 월→화→토로 바꿔도 최종 토인가.
3. 학습 전환 드롭다운으로 두 번째 학습을 보면 그 학습의 과제·조언·자료로 바뀌는가. 이전에 만든 학습은 조언 카드에 "AI 생성" 표시 없이 고정 안내문이 나오는가.
4. 새로 만든 학습(위저드에서 확정)은 조언 카드에 "AI 생성 · 참고용"이 붙는가.
5. 지난 요일을 골라도 연체·경고 표시가 전혀 없는가.
