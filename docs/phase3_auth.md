# PaceMate Phase 3 — 동의·익명 인증·데이터 기반 (AUTH)

**기준:** TASK.md Phase 3, docs/phase1_design.md §4, docs/phase2_prep.md Task 2.1·2.2
**상태:** 2026-10-19 구현 완료 → 검증팀 리뷰(docs/phase3_review_instructions.md) 반영 완료

---

## 1. 구현 범위

| Task | 구현 위치 | 내용 |
|---|---|---|
| 3.1 | `frontend/components/ConsentModal.tsx`, `AuthProvider.tsx` | 첫 방문 온보딩 모달(Phase 2 확정 문구 v1.0), 체크 후에만 `동의하고 시작하기` 활성화 |
| 3.2 | `frontend/lib/session.ts`, `AuthProvider.tsx` | 동의 버튼 이후에만 `signInAnonymously()` 실행. `동의하지 않음` → UID·저장 없이 안내 화면 |
| 3.3 | `POST /api/consent` | `user_id`(토큰)·`terms_version`·`privacy_agreed`·`ai_use_agreed`·`consented_at`만 저장. 현재 버전(v1.0)이 아니면 `TERMS_VERSION_MISMATCH` |
| 3.4 | `backend/auth.py` | `Authorization: Bearer <Firebase ID Token>`을 firebase-admin으로 검증, UID는 토큰에서만 결정 |
| 3.5 | `backend/store.py`, `firebase/firestore.rules`, `firebase/firestore.indexes.json` | Firestore 저장소, 모든 단건 접근에 소유권 검사(`_get_owned`), 목록·삭제 쿼리에 `user_id` 조건 강제 |
| 3.6 | `backend/main.py` | 목표 CRUD, 과제 CRUD(목표 소유권·월요일 주간 시작·요일/상태 값 검증) |
| 3.7 | `POST /api/user/delete-data`, `frontend/components/DeleteDataSection.tsx` | 확인 모달 → 전체 삭제 → 익명 계정 삭제 → 온보딩으로 복귀 |

## 2. 권한 규칙

- 토큰 없음/위조 → `401 UNAUTHORIZED`
- 토큰은 유효하나 현재 버전 동의 기록 없음 → `403 CONSENT_REQUIRED` (목표·과제·프로필 전체)
- 다른 UID 소유 문서 접근 → `403 FORBIDDEN`, 없는 문서 → `404 NOT_FOUND`
- 요청 본문의 `user_id`는 무시되고 토큰 UID로 저장
- 오류 응답은 모두 `{"detail": {"code", "message", "details"}}` 형식 (입력 검증 실패는 `422 VALIDATION_ERROR`)
- Firestore 보안 규칙: 클라이언트 직접 쓰기 전면 차단, 본인 문서 읽기만 허용. 실제 데이터 접근은 백엔드(Admin SDK) 경유

**삭제 전파 규칙:** 목표 삭제 → 하위 과제·기록·회고 삭제. 과제 삭제 → 하위 기록·회고 삭제. (기록 삭제는 과제에 전파되지 않음 — Phase 5)

## 3. 실행 모드

자격증명이 없어도 전체 흐름을 확인할 수 있도록 두 모드를 둔다.

| 구분 | 로컬 개발 (기본 예시) | 배포 |
|---|---|---|
| 백엔드 `AUTH_MODE` | `dev` — `dev-<uid>` 토큰 허용 | `firebase` |
| 백엔드 `STORE_BACKEND` | `memory` — 재시작 시 초기화 | `firestore` |
| 프론트 `NEXT_PUBLIC_AUTH_MODE` | `dev` — 무작위 UID 생성 | `firebase` |
| 비밀값 | 없음 | `FIREBASE_SERVICE_ACCOUNT_JSON` (Render 환경변수) |

- `AUTH_MODE=dev`는 Render(`RENDER` 환경변수 존재)에서 기동 시 즉시 실패하도록 막았다.
- 프론트 `NEXT_PUBLIC_FIREBASE_*` 값은 공개 식별자이며 비밀값이 아니다.

## 4. 데이터 삭제 요청 운영 절차 (Task 3.7)

**사용자 셀프 삭제 (기본 경로)**
1. 화면의 `내 학습 데이터 삭제 요청` → 확인 모달에서 `삭제`.
2. 백엔드가 토큰 UID 기준으로 `goals`, `tasks`, `study_logs`, `reflections`, `conversations`, `consent_records`, `users/{uid}`를 삭제하고 Firebase 익명 계정을 삭제한다.
3. 브라우저의 동의 표시·세션을 지우고 온보딩 모달로 돌아간다.

**운영자 대리 삭제 (사용자가 브라우저를 잃었거나 삭제 버튼을 쓸 수 없는 경우)**
1. 사용자에게 화면에 표시된 UID 앞 8자리를 받는다. (이름·연락처는 요구하지 않는다.)
2. Firebase 콘솔 → Authentication에서 해당 UID 계정을 찾아 전체 UID를 확인한다.
3. Firestore 콘솔에서 위 6개 컬렉션의 `user_id == <UID>` 문서와 `users/<UID>`를 삭제하고, Authentication 계정을 삭제한다.
4. 처리 결과를 요청 채널로 회신하고, 요청 기록에는 UID 앞 8자리와 처리일만 남긴다.

**베타 테스트 종료 후:** 테스트 종료 공지와 함께 전체 데이터 삭제 일정을 안내하고, 일정에 따라 테스트 프로젝트의 사용자 데이터를 일괄 삭제한다.

## 5. 검증 결과

- `backend/tests` 53건 통과 (Phase 3 신규 16건 + 검증팀 리뷰 반영 19건: 인증, 동의 게이트, 소유권 격리, CRUD, 삭제 전파, 데이터 삭제, 동의 멱등성, 수준 검증, 날짜/공백 검증, 배포 가드, Firebase 토큰 분기)
- 실서버(dev 모드) 스모크: 무토큰 401 → 동의 전 403 → 동의 201 → 목표 저장 201 → 타 UID 403 → 삭제 후 403, CORS 허용 Origin 200 / 비허용 400, Render에서 dev 인증 기동 거부
- 프론트 `npm run typecheck`, `npm run build` 통과

## 5-1. 검증팀 리뷰 반영 (docs/phase3_review_instructions.md)

전체 항목과 결정 사항은 `docs/phase3_review_instructions.md`(원본 지시)와 `docs/erd_current.md` §3(데이터 설계 결정)에 있다. 요약:

- **수준 설계:** `LevelItem.level`→`order`, Goal의 `*_level_num`→`*_level_order`로 이름 변경(점수처럼 읽히는 문제 해결). 5단계 고정 폐지(`ge=1, le=20`). 목표 수준은 현재 수준보다 **높아야만** 허용(동일 수준 거부). `PathRecommendationResponse`는 과정별 `levels[]`를 갖도록 재구성. 목표 생성 시 현재·목표 수준 설명 스냅샷(`current_level_description`/`target_level_description`, 선택)을 저장할 수 있게 추가.
- **계약 보완:** `PathRecommendationRequest.goal`(학습 목표), `PathRecommendationResponse.suggested_roles`(직무명 최대 5개), `PlanGenerateRequest.goal_id`/`course`(단일, 기존 `selected_courses` 대체)/`selected_role` 추가. `WeeklyTaskPlanItem.week_number` 제거, `suggested_weekday`를 `Weekday` 리터럴로 통일.
- **study_logs:** `started_at`/`ended_at`을 선택 필드로 스키마에 추가(동작 구현은 Phase 5).
- **동의 흐름(2-1):** `AuthProvider`가 `restoreSession()` 실패 시 새 UID를 만들지 않고 동의 표시를 지운 뒤 모달로 되돌아가도록 수정.
- **미구현 API 인증·오류 형식(2-2):** study-logs 4개, `/api/data/summary`, `/api/dashboard/summary`, conversations 4개에 `require_consented_uid` 적용(무토큰 401). `/api/resources`는 공개 읽기 전용 카탈로그라 인증 없이 유지(결정, 문서화 완료). 501 응답을 `{"detail":{"code":"NOT_IMPLEMENTED",...}}` 형식으로 통일.
- **데이터 삭제 실패 분리(2-3):** Firestore 삭제 후 Firebase 계정 삭제가 실패해도 데이터 삭제는 유지하고 `status: "auth_cleanup_pending"`으로 구분 응답(200). 프론트는 이 경우에도 동의 상태를 정리한다.
- **동의 멱등성(2-4):** 같은 UID·같은 버전으로 재호출하면 기존 기록을 200으로 반환, 새로 만들지 않는다. 버전이 바뀌면 새 기록(201)을 만든다.
- **도메인 검증(2-5):** `target_date`가 오늘보다 이전이면 400. `field`/`course`/`title`이 공백만 있으면 422(Pydantic validator). 주간 시간 총량 검증은 Phase 4에서 적용 예정(현재 범위 아님).
- **배포 가드(2-6):** `STORE_BACKEND=memory`도 Render(`RENDER` 환경변수 존재) 기동 시 `RuntimeError`로 거부하도록 `store.assert_safe_store_config()` 추가, `main.py` 시작 시 호출. `.env.example`에 배포 금지 경고 주석 추가.
- **저장소 위생:** `대화기록.md`를 `.gitignore`에 추가(비밀값 없음 확인).
- **보류(여유 권장 사항, 미반영):** 루트/백엔드 `pytest.ini` 통합, `require_consented_uid`의 `users` 문서 재조회 캐싱, `delete_goal`의 N+1 쿼리 최적화, 프론트 `apiRequest` 타임아웃·재시도. 모두 동작에 영향 없는 개선이라 범위 밖으로 남겨둠.

## 6. 미완료·사용자 조치 필요

- **Firebase 프로젝트 연결 (Task 0.5):** 실제 Firebase 모드 검증에는 다음이 필요하다.
  1. Firebase 콘솔에서 Authentication → 로그인 방법 → **익명** 사용 설정
  2. Firestore 데이터베이스 생성 후 `firebase/firestore.rules`, `firebase/firestore.indexes.json` 배포
  3. 웹 앱 등록 후 `NEXT_PUBLIC_FIREBASE_*` 값을 `frontend/.env.local`에 입력
  4. 서비스 계정 키 JSON을 `backend/.env`의 `FIREBASE_SERVICE_ACCOUNT_JSON`(한 줄 JSON)에 입력 — 저장소에 커밋 금지
- 브라우저에서 모달 클릭 흐름은 수동 확인이 필요하다 (자동 브라우저 테스트 도구 미사용).
