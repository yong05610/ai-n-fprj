# Phase 5C 수정 보고 — R1 동시 학습 최대 2개 규칙

**기준:** docs/phase5c_fix_instructions.md (대상: 커밋 2db65f8 이후)
**상태:** 2026-10-22 R1 수정 완료, 재검증 대기. Phase 6 은 시작하지 않았다.
**환경:** 서버는 `AUTH_MODE=dev STORE_BACKEND=memory`(백엔드, 포트 8123)와 `NEXT_PUBLIC_AUTH_MODE=dev NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8123`(프론트, 포트 3123)을 명령줄로 덮어써서 띄웠고 확인 후 종료했다. `.env`, `.env.local` 은 수정하지 않았다. 설계 문서(docs/multi_goal_design.md, erd_current.md, phase1_design.md)는 고치지 않았다.

## 1. 변경 내용

**`backend/main.py` — `_check_goal_period_overlap`** (두 생성 경로 `POST /api/plan/confirm`, `POST /api/goals` 가 같은 함수를 쓰고 입력 검증 뒤 저장 직전에 호출하는 구조, plan/confirm 의 멱등 조회가 검사보다 앞인 순서는 그대로)
- 규칙: 새 구간 [start_date, target_date](양 끝 포함)의 **어느 하루라도** status=active 인 기존 학습이 이미 2개(`MAX_CONCURRENT_GOALS`)이면 409 `GOAL_PERIOD_OVERLAP`. 기존 1개만 겹치면 허용, 기존 2개여도 새 구간의 같은 날에 동시에 걸리지 않으면 허용. completed/archived 는 세지 않는다.
- 계산: 새 구간과 겹치는 기존 학습들의 경계(시작일, 종료일 + 1일, 새 구간으로 자른 값)로 새 구간을 조각내고 조각마다 동시 학습 수를 센다(하루씩 반복하지 않음). 처음으로 2개 이상이 되는 연속 구간을 `conflict_from ~ conflict_to` 로 보고한다.
- 오류 응답: 메시지 "한 날에 진행할 수 있는 학습은 최대 2개예요. {from} ~ {to} 에 이미 '{A}'({기간}), '{B}'({기간}) 두 학습이 있습니다. 학습 시작일이나 목표 완료일을 조정해 주세요." `details` = `max_concurrent: 2`, `conflict_from`, `conflict_to`, `overlaps`(그 구간에 걸린 학습 전부, 일정 빠른 순), 그리고 기존 단일 필드(`goal_id`, `course`, `start_date`, `target_date`)는 첫 항목으로 유지. 로그에는 사용자 입력 원문을 남기지 않는다(예외 메시지로만 전달).
- `GET /api/goals`, 학습 전환, 대시보드, 분석 API 등 다른 코드는 바꾸지 않았다.

**`frontend/components/LearningPathWizard.tsx`**
- 입력칸 아래 안내문: "같은 기간에 진행할 수 있는 학습은 최대 2개예요."
- 저장 오류(하단): "같은 기간에 이미 학습이 2개 있어 저장하지 못했어요. 위의 학습 시작일·목표 완료일을 바꾸면 다시 저장할 수 있어요. 입력한 내용은 그대로 남아 있어요."
- 날짜 입력칸 아래의 서버 메시지 표시(겹치는 학습 목록과 기간)와 "날짜를 바꾸면 오류가 지워짐" 동작은 그대로다.

## 2. 테스트

- **backend pytest: 274 passed** (직전 258 + 신규 16: 신규 파일 14건 + 기존 테스트를 둘로 나눈 2건). frontend: `npm run typecheck` 통과, `npm test` 21건 통과, `npm run build` 통과. 문구를 직접 검사하는 프론트 테스트는 없어 갱신할 것이 없었다.
- **기대값을 새 규칙에 맞게 고친 기존 테스트 (바꾼 목록)**
  - `test_phase5b_multi.py`: `test_same_period_is_rejected_with_409_and_details` → "같은 기간 2번째는 허용"과 "3번째는 409(상세에 두 학습, max_concurrent, conflict 구간)"로 분리, `test_rejection_saves_nothing`(2개 있는 상태에서 3번째 거부로), `test_overlap_by_a_single_day_is_rejected`(2개가 하루 공유하는 날에 걸쳐 거부로), `test_new_period_enclosing_existing_is_rejected`(서로 겹치는 2개를 감싸면 거부 / 서로 겹치지 않는 2개를 감싸면 허용, 두 테스트로 분리), `test_goal_post_rejects_overlap_with_active_goal`(2번째 허용, 3번째 거부로), `test_legacy_goal_takes_part_in_overlap_check`(옛 목표 + 하나 더로 3번째 거부, `created_at` 대체 시작일이 계산에 들어가는지 확인).
  - `test_phase5b_fix2.py`: `test_reported_scenario_far_future_goal_...`(기존 1개는 허용, 2개가 되면 감싸는 새 학습 거부), `TestAllOverlapsReported` 두 테스트(겹치는 2개를 한 번에 가로지르면 둘 다 안내, 위기 구간에 걸린 학습만 목록에 포함).
  - `test_phase4_plan.py`: 변경 없음. 두 테스트(`test_different_client_request_id_creates_a_new_goal`, `test_omitting_client_request_id_keeps_old_always_create_behavior`)는 서로 겹치지 않는 기간을 쓰므로 새 규칙에서도 그대로 통과한다.
- **신규 `backend/tests/test_phase5c_r1.py` (14건):** 지시서 예시 4건(A 11/1~11/30, B 11/10~11/20 으로 날짜를 옮김 — 시작일이 오늘 이후여야 해서. C 11/12~11/15 거부, 11/21~11/25 허용, 11/1~11/9 허용, 11/9~11/12 는 11/10~11/12 에 2개라 거부), 같은 기간 1개면 201, 하루만 공유하는 2개에 하루 걸쳐도 거부/양 끝 다른 날은 허용(경계 포함), 서로 겹치지 않는 2개를 감싸는 새 학습 허용, completed/archived 미계산, 거부 시 아무것도 저장되지 않고 현재 학습 유지, 이미 만든 목표의 멱등 재시도는 나중에 기간이 붐벼도 200, 타 UID 격리, 과거 시작일 400, `POST /api/goals` 경로도 같은 규칙.

## 3. 실제 서버 확인 (빈 포트, dev 모드, 환경변수 덮어쓰기)

오늘 + 10일을 기준일(base)로 A = base ~ base+30, B = base+9 ~ base+19(지시서의 A 10/1~10/31, B 10/10~10/20 과 같은 모양)를 만든 뒤 HTTP 로 호출:

| 호출 | 지시서 예시 | 결과 |
|---|---|---|
| C base+11 ~ base+14 | 10/12~10/15 거부 | **409**, conflict 구간 11/12~11/15 |
| C base+20 ~ base+24 | 10/21~10/25 허용 | **201** |
| C base ~ base+8 | 10/1~10/9 허용 | **201** |
| C base+8 ~ base+11 | 10/9~10/12 거부 | **409**, conflict 구간 11/10~11/12(2개가 겹치는 처음 연속 구간) |

허용/거부가 지시서와 같다. 이어서 같은 서버에 붙인 실제 브라우저(Chrome)에서 A, B 와 기간이 겹치는 위저드 초안을 저장해 보았다: 입력칸 아래 안내문 "같은 기간에 진행할 수 있는 학습은 최대 2개예요.", 서버 메시지에 'A', 'B' 의 이름과 기간 표시, 하단 문구 "같은 기간에 이미 학습이 2개 있어 저장하지 못했어요…", 목표 완료일을 바꾸자 오류가 지워지는 것을 확인했다(이후 "입력 조건이 바뀌어 초안이 최신 상태가 아닙니다" 안내가 보이는 것은 기존 동작).

## 4. 미검증

- 위저드의 AI 호출 구간(분야, 직무 예시, 추천, 계획 생성)은 AI 키 없는 확인 환경이라 실행하지 않았다. 오류 화면은 저장된 초안을 복원해서 확인했다.
- Firebase 실연동 미검증.

## 5. 열린 결정

1. 같은 날에 걸린 학습이 3개 이상(과거 데이터나 일정 변경으로 생긴 경우)인 연속 구간도 "겹치는 학습 전부"로 모두 나열한다. 이때 메시지의 "두"를 개수로 바꿔 쓴다(예: "3 학습"). 문구를 다듬을지.
2. 기존 학습의 일정 변경(`PATCH /api/goals/{id}`)은 지시대로 계속 검사하지 않는다. 그 결과 3개 이상이 한 날에 생길 수 있고, 이후 새 학습 생성은 거부되지만 기존 학습은 그대로 둔다.

---

보고 후 멈추고 검증팀 재검증을 기다립니다. Phase 6 은 시작하지 않았습니다.
