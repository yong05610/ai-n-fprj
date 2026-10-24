# 실행 모드 가시화 검증 결과 (PM, 2026-10-25)

**대상:** 커밋 9b6df2f, 지시서 docs/ops_fix_instructions_mode_visibility.md, 개발팀 보고 docs/ops_fix_report_mode_visibility.md
**판정:** 승인(백엔드 시작 로그와 `/health`는 PM 이 실제 서버로 확인). 화면 띠는 개발팀 Chrome 확인 보고만 있어 PM 미검증, 사용자가 눈으로 확인하는 항목으로 남긴다.

## 1. 직접 확인한 것
- backend `pytest` **772 passed**(직전 756 + 16), frontend `typecheck` 통과, `npm test` **139 passed**(직전 132 + 7), `npm run build` 통과(보고와 일치).
- **실제 서버 시작(빈 포트 8231, 8232, 시작 후 종료 확인):**

| 조합 | `/health` | 시작 로그 |
|---|---|---|
| dev + memory | `auth_mode: dev`, `store_backend: memory` | `INFO startup auth_mode=dev store_backend=memory`, `WARNING data is NOT persisted: store_backend=memory (data disappears when the server stops)`, `WARNING auth_mode=dev: fake dev tokens are accepted` |
| dev 인증 + firestore | `auth_mode: dev`, `store_backend: firestore` | `INFO startup auth_mode=dev store_backend=firestore`, dev 토큰 경고 |
- 로그와 `/health` 에 비밀값, URL, 프로젝트 ID, UID 없음(개발팀 테스트 + PM 이 출력 확인). 사용자의 8001 서버는 건드리지 않음.
- **사용자의 실제 서버(8001) 상태(읽기 전용 확인):** `--reload` 로 새 코드가 적용되어 `/health` 가 `auth_mode: dev`, `store_backend: memory` 를 보여 준다. 즉 이 가시화가 문제의 서버 상태를 정확히 드러낸다. 가짜 dev 토큰 조회는 403(dev 인증 켜짐). **아직 깨끗한 터미널에서 Firebase 모드로 다시 시작하지 않은 상태**다.

## 2. 미검증
- Firebase 프론트 빌드에서 띠가 보이지 않는 화면(확인용 빌드가 dev 라서 개발팀도 단위 테스트로만 확인), 실제 Firebase 모드 서버의 시작 로그와 `/health`, 모바일 폭, 화면 띠의 실제 모습(PM 은 보지 못했다).

## 3. 열린 결정 처리
- 터미널에 남은 환경변수가 `--env-file` 값을 덮어쓰는 규칙은 바꾸지 않는다(지시대로). 지금은 시작 로그, `/health`, 화면 띠로 바로 알아볼 수 있다. 더 강하게 막는 방법(예: 서버 시작 시 `.env` 와 환경변수가 다르면 시작을 거부하거나 경고)은 필요하면 별도 지시로 검토한다(재발하면 도입).

## 4. 사용자가 확인할 것
1. 서버를 깨끗한 새 터미널에서 Firebase 모드로 다시 시작한 뒤, 브라우저 주소 http://localhost:8001/health 를 열어 `"auth_mode":"firebase","store_backend":"firestore"` 인지 본다(지금은 `dev`, `memory`).
2. 화면 상단에 "개발 모드예요…" 띠가 **사라졌는지** 본다(Firebase 모드에서는 보이지 않아야 한다).
