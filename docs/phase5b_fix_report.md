# Phase 5B 수정 보고 (P5B-1)

**기준:** docs/phase5b_fix_instructions.md (대상: 커밋 b0d2de9)
**상태:** 2026-10-22 수정 완료, 재검증 대기. Phase 6 은 시작하지 않았다.

## 1. 수정한 항목

**P5B-1 (필수) 현재 학습을 삭제하면 다른 진행 중 학습이 있어도 "학습 없음"이 되던 문제**
- `backend/main.py`: `_fall_back_active_goal(db, uid, leaving_goal_id)` 추가. 나가는 목표가 `active_goal_id` 일 때만, 남은 `status=active` 목표 중 가장 최근 등록(`_goal_recency_key`)으로 `active_goal_id` 를 옮기고, 남은 것이 없으면 null. 다른 목표가 나가면 건드리지 않는다.
- 호출 경로 두 곳: `DELETE /api/goals/{id}`, 그리고 `PATCH /api/goals/{id}` 로 status 가 completed/archived 가 될 때(현재 학습이 비활성이 되는 유일한 경로).
- 정렬 기준은 `GET /api/goals` 와 같은 `_goal_recency_key`(created_at, 보조 키 start_date)를 공유한다. 두 곳의 정의가 어긋나지 않는다.
- 프론트 변경은 없다. 서버가 `active_goal_id` 를 옮기므로 대시보드 상단, 실행 화면, 전환 드롭다운이 같은 학습을 가리킨다.

**P5B-2 참고 항목 처리:** `docs/post_mvp_backlog.md` 에 "지난 주 보기"와 "POST /api/goals 멱등" 두 후속 후보를 기록했다(PM 지시). 코드 변경은 없다.

## 2. 테스트

- backend `python -m pytest -q`: **232 passed** (이전 225 + 신규 7).
- 신규: 현재 학습 삭제 시 남은 최근 활성 학습으로 이동(대시보드 제목과 overview 일치 확인), completed/archived 목표 건너뜀, 남은 활성 학습이 없으면 null, 다른 학습 삭제 시 유지, 현재 학습을 completed/archived 로 바꿀 때 같은 규칙, 현재가 아닌 학습의 상태 변경은 유지, 타 UID 영향 없음.
- 기존 테스트 2건 수정: `test_deleting_current_goal_clears_active_goal_id`(기대값 null → 남은 학습 A 로 변경, 이름도 변경), `test_stale_active_goal_id_still_returns_overview`(이제 삭제로 stale id 가 생기지 않으므로 저장소에서 직접 존재하지 않는 id 를 넣어 "깨진 id 에서도 대시보드가 200" 을 계속 검증).
- frontend 는 변경이 없어 다시 돌리지 않았다(마지막 결과: typecheck, npm test 6건, build 통과).

## 3. 실제 서버 HTTP 재현 (수정 후)

빈 포트 8123, dev 모드, 확인 후 종료. 지시서의 재현 시나리오(A, C 확정 → C 삭제):
```
before: active_goal_id == C
DELETE C -> 200
after:  active_goal_id == A, 대시보드 active_goal_title 이 A, goals_overview = [A]
DELETE A -> 200, active_goal_id = null
```
수정 전에는 C 삭제 후 active_goal_id 가 null 이었다(지시서 재현 결과). 수정 전 코드를 되돌려 다시 재현하지는 않았다.

## 4. 미검증

- 브라우저 화면(B.6~B.8)은 이전 보고서 §5 와 같이 미검증이다. 사용자 화면 확인 후 결과를 받는다.
- Firebase 실연동 미검증.

---

보고 후 멈추고 검증팀 재검증을 기다립니다. Phase 6 은 시작하지 않았습니다.
