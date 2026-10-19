# Phase 5 수정 보고 (검증팀 지시 반영)

**기준:** docs/phase5_fix_instructions.md (대상: docs/phase5_report.md 구현, 커밋 898504f)
**상태:** 2026-10-20 수정 완료, 재검증 대기. Phase 6은 시작하지 않았다.

---

## 1. 수정한 항목과 변경 파일

| 항목 | 내용 | 파일 |
|---|---|---|
| P5-1 (필수) | `finish_timer`가 활성 타이머 확인보다 `client_request_id` 멱등 조회를 먼저 한다. 일치하는 기록이 있으면 활성 타이머 상태와 무관하게 200과 기존 기록을 반환한다. 남은 활성 타이머가 같은 과제(task_id)를 가리키면(첫 시도가 기록 생성 후 타이머 해제 전에 실패한 경우) 그때만 정리한다. | `backend/main.py` (`finish_timer`) |
| P5-2 (필수) | `delete_goal`이 하위 과제를 지울 때마다 `_clear_active_timer_for_task`를 호출한다(기존에 `delete_task`에는 있었지만 `delete_goal`의 자체 루프에는 없었다). `finish_timer`는 종료 시점에 과제 존재·소유권을 다시 확인해, 없으면 타이머를 정리하고 `409 TIMER_TASK_GONE`을 반환한다. | `backend/main.py` (`delete_goal`, `finish_timer`) |
| P5-3 (중) | `Dashboard.tsx`의 `toggleTask`가 성공 후 `load({ silent: true })`로 요약을 다시 불러온다. `silent`는 전체 화면이 "불러오는 중"으로 바뀌지 않게 로딩 상태 전환을 건너뛴다. | `frontend/components/Dashboard.tsx` |
| P5-4 (중) | `get_dashboard_summary`가 이번 주 완료 과제도 `today_tasks`에 포함하고 `is_completed`를 실제 값으로 채운다. 우선순위: 오늘 요일 일치 미완료 → 나머지 미완료(순서대로) → 완료 과제. 상한 5(`TODAY_TASKS_LIMIT`, 명시적 상수)는 유지하되 완료 과제가 먼저 잘린다. 이번 주 과제가 1개 이상이고 전부 완료되면 `all_tasks_completed_this_week=true`를 반환하고, 프론트는 "이번 주 과제를 모두 완료했어요 🎉"를 보여준다. | `backend/schemas.py` (`DashboardSummaryResponse.all_tasks_completed_this_week`), `backend/main.py` (`get_dashboard_summary`), `frontend/components/Dashboard.tsx` |
| P5-5 (권장) | `ExecutionScreen`의 타이머 패널에 "타이머 취소" 버튼을 추가했다. 팝업 대신 같은 패널 안의 인라인 확인("기록을 만들지 않고 취소할까요? [취소 확정] [아니요]")을 쓴다. | `frontend/components/ExecutionScreen.tsx` |
| P5-6 (권장) | `list_study_logs`가 기록마다 회고를 따로 조회하던 것을 `_attach_reflections_bulk`로 바꿔, 사용자의 회고 전체를 한 번만 읽어 `study_log_id`로 묶는다. | `backend/main.py` (`_attach_reflections_bulk`, `list_study_logs`) |
| P5-7 (문서화) | `start_timer`에 비원자성 한계를 코드 주석으로 남기고 `docs/phase5_report.md` §10에 같은 내용을 기록했다. 코드는 바꾸지 않았다(실제 수정은 Firestore 트랜잭션 전환 시점). | `backend/main.py` (주석), `docs/phase5_report.md` |
| 경미 1 | 대시보드 4번째 카드가 1번째와 같은 진행률을 반복하던 것을 "주간 목표 달성률"(이번 주 학습 시간 ÷ 주간 목표 시간)로 바꿨다. | `frontend/components/Dashboard.tsx` |
| 경미 2 | `list_study_logs`가 200건을 넘으면 응답 헤더 `X-Study-Logs-Truncated: true`를 추가하고, `ExecutionScreen`이 이를 읽어 "최근 200건만 표시됩니다"를 보여준다. 기존 `apiRequest`의 응답 타입(배열)을 바꾸지 않으려고 헤더를 쓰고, 이를 읽는 `apiRequestWithHeaders`를 `lib/api.ts`에 새로 추가했다(기존 `apiRequest` 호출부는 전혀 바뀌지 않는다). | `backend/main.py` (`list_study_logs`), `frontend/lib/api.ts`, `frontend/components/ExecutionScreen.tsx` |

추가로 `TASK.md` 5.2의 상태 머신 표기를 지시대로 `idle → running → stopped → saved (일시정지는 MVP 제외, 사용자 테스트 후 개선 후보)`로 정리했다.

## 2. 테스트

- **신규 테스트 11건** (`backend/tests/test_phase5_exec.py`): P5-1 멱등 재시도 200 확인 + 기존 "일치 키 없으면 여전히 409" 회귀 가드, P5-2(목표 삭제 시 타이머 정리, 이미 삭제된 과제의 타이머 종료 시도 시 `TIMER_TASK_GONE`), P5-4(완료 과제가 `is_completed=true`로 보임, 체크 해제 시 다시 `false`, `all_tasks_completed_this_week` 플래그, 상한 내 우선순위), P5-6(벌크 회고 부착이 올바른 회고를 연결하는지), 경미 2(200건 초과 시 헤더, 이하일 때 헤더 없음).
- **backend pytest:** 185건 전부 통과 (기존 174 + 신규 11). `python -m pytest -q` → `185 passed`.
- **frontend:** `npm run typecheck` 통과, `npm run build` 통과, `npm test`(week.ts, 6건) 통과.

## 3. P5-1·P5-2 실제 서버 HTTP 재현 (수정 후)

dev 모드(`AUTH_MODE=dev`, `STORE_BACKEND=memory`) uvicorn을 빈 포트에 띄워 확인했다(종료 후 서버 정리함).

```
=== P5-1: finish 멱등 재시도 ===
first finish: 201 (기록 생성)
retry finish (수정 전이었다면 409 TIMER_NOT_RUNNING): 200, 같은 기록 id 반환
기록 수: 1건 (중복 생성 없음 — 이 부분은 수정 전에도 지켜지고 있었다. 바뀐 것은 재시도의 응답 코드다)

=== P5-2: 목표 삭제가 활성 타이머를 정리하는지 ===
목표 삭제 전 활성 타이머: active=true, task_id=<삭제 대상 과제>
DELETE /api/goals/{id} → 200
목표 삭제 후 활성 타이머 (수정 전이었다면 여전히 active=true): active=false
```

검증팀이 재현한 "수정 전" 동작은 직접 되돌려 재현하지 않았다 — 지시서에 이미 재현 결과가 있고, 고친 코드의 동작이 지시서가 요구한 것과 일치함을 위 실행으로 확인했다.

## 4. 사용자가 직접 눌러 볼 시나리오 (P5-3·P5-4·P5-5 확인 단계 추가)

기존 `docs/phase5_report.md` §8 시나리오에 이어서:

10. 대시보드에서 과제를 체크 → **새로고침 없이** 상단 "완료 학습 과제"와 "전체 진행률" 숫자가 즉시 바뀌는지 확인(P5-3).
11. 이번 주 과제를 전부 완료 → "이번 주 과제를 모두 완료했어요 🎉" 안내가 보이는지, 체크리스트에서 완료한 과제가 사라지지 않고 체크 표시로 남아 있는지, 체크를 다시 눌러 미완료로 되돌릴 수 있는지 확인(P5-4).
12. 학습 실행 기록에서 타이머를 시작한 뒤 "타이머 취소"를 눌러 인라인 확인("아니요"/"취소 확정")이 뜨는지, 취소 후 기록이 생기지 않고 "학습 시작" 버튼으로 돌아오는지 확인(P5-5).

## 5. 미검증 항목

- **브라우저 UI:** 이 환경에 브라우저 자동화 도구가 없어 여전히 직접 조작해 확인하지 못했다. 위 §3의 실제 HTTP 재현과 `npm run build`/`typecheck`/`test`로 대신 확인했다.
- **Firebase 실연동(Task 0.5):** 미검증. P5-7(타이머 시작 비원자성)은 Firestore 트랜잭션 연결 전에는 애초에 완전히 검증할 수도 없는 항목이다.

---

보고 후 멈추고 검증팀 재검증을 기다립니다. Phase 6은 시작하지 않았습니다.
