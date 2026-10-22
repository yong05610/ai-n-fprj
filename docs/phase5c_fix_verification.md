# Phase 5C 수정(R1 동시 학습 최대 2개) 검증 결과 (PM, 2026-10-23)

**대상:** 커밋 7dff69f, 지시서 docs/phase5c_fix_instructions.md, 개발팀 보고 docs/phase5c_fix_report.md
**판정:** R1 승인 (dev 모드 기준). 브라우저 화면 조작과 Firebase 실연동은 미검증.

## 1. 직접 확인한 것
- 코드 읽기: `backend/main.py` `_check_goal_period_overlap`. 새 구간을 기존 학습의 경계(시작일, 종료일+1)로 쪼개 조각별 동시 학습 수를 센다. 양 끝 포함, status=active 만 계산, 2개 이상인 조각이 있으면 409 `GOAL_PERIOD_OVERLAP`. `details` 에 `max_concurrent`, `conflict_from`, `conflict_to`, `overlaps`, 기존 단일 필드 호환. 검사는 생성 경로(`POST /api/plan/confirm`, `POST /api/goals`)에만 있고 PATCH 에는 없다(의도된 규칙).
- 프론트 문구 두 곳(안내문, 저장 오류)이 지시서대로 바뀐 것을 diff 로 확인.
- backend `python -m pytest`: **274 passed**. frontend `npm run typecheck` 통과, `npm test` 21 passed, `npm run build` 통과.
- 실제 서버: 빈 포트 8211, `AUTH_MODE=dev STORE_BACKEND=memory` 환경변수 덮어쓰기, `.env` 미수정, 확인 후 종료. A=base~base+30, B=base+9~base+19 를 만든 뒤 호출.

| 호출 | 지시서 기대 | 결과 |
|---|---|---|
| C base+11~+14 | 거부 | 409 (conflict 11/13~11/16) |
| C base+20~+24 | 허용 | 201 |
| C base+0~+8 | 허용 | 201 |
| C base+8~+11 | 거부 | 409 (conflict 11/10~11/13) |

네 번째는 앞에서 만든 C(base~+8)가 있어 base+8 하루도 A 와 합쳐 2개이므로 충돌 구간이 B 시작일(base+9)보다 하루 앞서 시작한다. 규칙대로 맞는 결과다.

## 2. 열린 결정 처리
1. 3개 이상 겹침 시 메시지의 "두"를 숫자로 바꾸는 문구: 현재 동작 유지. 3개 이상은 일정 변경으로만 생기고 드물다.
2. 실행 중 일정 변경(PATCH)으로 한 날에 3개 이상이 되는 것: **사용자 확인, 의도된 규칙(통제하지 않음).** 계획 수립 시점에만 2개를 검사한다. 설계 문서(multi_goal_design.md §1·§7, erd_current.md, phase1_design.md)에 이미 명시되어 있어 수정 없음.

## 3. 미검증
- 위저드 브라우저 화면(안내문, 오류 표시, 날짜 변경 시 오류 해제): 개발팀 보고만 있고 PM 이 직접 보지 않았다.
- Firebase 실연동.
