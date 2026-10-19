# PaceMate Phase 3 — 동의·익명 인증·데이터 기반 (AUTH)

**기준:** TASK.md Phase 3, docs/phase1_design.md §4, docs/phase2_prep.md Task 2.1·2.2
**상태:** 2026-10-19 구현 완료 (검증 대기)

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

- `backend/tests` 34건 통과 (Phase 3 신규 16건: 인증, 동의 게이트, 소유권 격리, CRUD, 삭제 전파, 데이터 삭제)
- 실서버(dev 모드) 스모크: 무토큰 401 → 동의 전 403 → 동의 201 → 목표 저장 201 → 타 UID 403 → 삭제 후 403, CORS 허용 Origin 200 / 비허용 400, Render에서 dev 인증 기동 거부
- 프론트 `npm run typecheck`, `npm run build` 통과

## 6. 미완료·사용자 조치 필요

- **Firebase 프로젝트 연결 (Task 0.5):** 실제 Firebase 모드 검증에는 다음이 필요하다.
  1. Firebase 콘솔에서 Authentication → 로그인 방법 → **익명** 사용 설정
  2. Firestore 데이터베이스 생성 후 `firebase/firestore.rules`, `firebase/firestore.indexes.json` 배포
  3. 웹 앱 등록 후 `NEXT_PUBLIC_FIREBASE_*` 값을 `frontend/.env.local`에 입력
  4. 서비스 계정 키 JSON을 `backend/.env`의 `FIREBASE_SERVICE_ACCOUNT_JSON`(한 줄 JSON)에 입력 — 저장소에 커밋 금지
- 브라우저에서 모달 클릭 흐름은 수동 확인이 필요하다 (자동 브라우저 테스트 도구 미사용).
