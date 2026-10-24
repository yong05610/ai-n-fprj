# 운영 수정 보고서 — 실행 모드(dev/Firebase, 메모리/Firestore) 가시화

작성: 개발팀, 2026-10-25. 기준: docs/ops_fix_instructions_mode_visibility.md. Phase 7 은 시작하지 않았다.

## 요약
- 서버 시작 로그, `GET /health` 확장, 화면 안내 띠 세 가지를 모두 구현했다. 인증·저장소 동작, 환경변수 규칙, 배포 설정은 바꾸지 않았다.
- 테스트: backend pytest **772 통과**(756 → 새 16), frontend `npm test` **139 통과**(132 → 새 7), typecheck 와 build 통과.
- 실제 서버(`AUTH_MODE=dev STORE_BACKEND=memory`, 빈 포트 8123)와 실제 Chrome 에서 띠 표시를 확인했다(10개 항목 통과). Firebase 모드 값은 가짜 `/health` 응답으로 확인했다.

## 변경 내용
| 항목 | 내용 | 파일 |
|---|---|---|
| 시작 로그 | 앱이 뜰 때(`lifespan`) `INFO startup auth_mode=<dev\|firebase> store_backend=<memory\|firestore>` 한 줄. memory 이면 `WARNING data is NOT persisted: store_backend=memory (data disappears when the server stops)` 한 줄 더. dev 인증이면 `WARNING auth_mode=dev: fake dev tokens are accepted (local development only)` 한 줄 더(저장소는 Firestore 인데 dev 인증인 조합도 놓치지 않기 위해 추가). 값은 모드 이름뿐이며 비밀값·URL·프로젝트 ID·UID 가 없다 | `backend/main.py` (`running_modes`, `log_startup_modes`) |
| 로그가 실제로 보이게 | uvicorn 은 `pacemate.*` 로거의 INFO 를 콘솔에 내보내지 않는다(처음 만들 때 확인). 그래서 처리 중인 로깅 설정이 없으면(루트 로거에 핸들러 없음) 시작 로거가 자기 핸들러를 달아 콘솔에 나오게 했다. 실제 uvicorn 실행에서 4줄이 출력됨을 확인(아래) | `backend/main.py` |
| `GET /health` | `{status, service, auth_mode, store_backend}`. 인증 불필요, 비밀값 없음. 값은 코드가 분기하는 기준 그대로 정규화(`dev`/`firebase`, `memory`/`firestore`; 공백·대소문자 무시, 그 밖의 값은 firebase/firestore 로 본다). 배포(`RENDER`)에서는 memory/dev 가 시작 때 거부되므로 항상 firebase/firestore | `backend/main.py` |
| 화면 띠 | 앱 셸이 뜬 뒤 `/health` 를 한 번 읽는다(5초 제한). `memory` 이면 "개발 모드예요. 서버를 끄면 데이터가 사라져요. (dev / memory)", dev 인증 + Firestore 이면 "개발용 인증 모드예요. 가짜 토큰으로 접속돼요. (dev / firestore)", 프론트 빌드가 `NEXT_PUBLIC_AUTH_MODE=dev` 이면 서버와 무관하게 "프론트가 dev 인증 모드예요."를 같은 띠에 추가(서버가 firebase 이면 "서버 인증은 firebase 예요. 서로 맞는지 확인해 주세요."). Firebase/Firestore + Firebase 프론트는 아무것도 보이지 않음. `/health` 실패·옛 서버(필드 없음)는 서버 줄 없음(기존 오류 처리 유지), 서버가 준 모드 이름은 소문자 영문 20자까지만 화면에 나온다 | `frontend/lib/modeBanner.ts`, `components/ModeBanner.tsx`, `app/page.tsx`, `app/globals.css` |
- 계약 문서: `/health` 는 `docs/phase1_design.md` 에 행이 없어 갱신할 항목이 없다.

## 실제 서버 시작 로그 (uvicorn, `AUTH_MODE=dev STORE_BACKEND=memory`)
```
INFO:     Waiting for application startup.
INFO:     startup auth_mode=dev store_backend=memory
WARNING:     data is NOT persisted: store_backend=memory (data disappears when the server stops)
WARNING:     auth_mode=dev: fake dev tokens are accepted (local development only)
INFO:     Application startup complete.
```
`GET /health` → `{"status":"ok","service":"pacemate-api","auth_mode":"dev","store_backend":"memory"}`.

## 화면 변경 (구현에만 있음(의도적), 목업에 없음)
- 위치: 상단 바 바로 아래, 페이지 위(앱 셸의 `workspace` 안). 상단 바는 그대로 고정, 띠는 일반 흐름이라 스크롤하면 위로 올라간다.
- 모양: 연한 주황 배경(`#fff6e5`), 얇은 아래 테두리, 11px 굵은 글씨, 높이 32px(한 줄), 두 줄 안내는 줄바꿈 없이 가로로 이어서 표시. 5C 앱 셸과 같은 여백(`clamp(20px, 3vw, 42px)`)을 쓴다.
- 확인한 값(캡처 `mode_dev_memory.png`, 임시 폴더): 상단 바 0~68px, 띠 68~100px, 본문 100px~; 겹침 없음, 사이드바·화면 이름·대시보드 그대로.
- 문구 예: "개발 모드예요. 서버를 끄면 데이터가 사라져요. (dev / memory)   프론트가 dev 인증 모드예요."

## 테스트
- backend 새 16건(`test_ops_mode_visibility.py`) + 기존 `/health` 테스트 기대값 갱신 1건:
  - `/health` 모드 4가지 조합(dev/memory, firebase/firestore, dev/firestore, firebase/memory), 공백·대소문자, 알 수 없는 값, 인증 없이 호출, `RENDER` 설정 시 firebase/firestore, 응답에 비밀값·URL·UID 없음
  - 시작 로그 형식(`caplog`): memory+dev 는 INFO 1 + WARNING 2, firebase+firestore 는 INFO 1 만, 조합별 경고 종류, 앱 시작(lifespan)에서 실제로 기록됨, 비밀값·URL·프로젝트 ID·UID·CORS 값 없음, 로깅 설정이 없을 때 자기 핸들러로 출력됨
- frontend 새 7건(`modeBanner.test.ts`): memory, dev 인증+영속 저장소, firestore+firebase(표시 없음), `/health` 로딩·실패, 프론트 dev(서버 무관), 프론트 dev + Firebase 서버(불일치 안내), `parseHealth` 검증.
- 기존 테스트 변경: `test_health_and_docs.py::test_health_check` 기대값에 `auth_mode`, `store_backend` 추가(테스트 환경은 dev/memory).

## 실제 확인 결과 (실제 Chrome, 빈 포트 8123/3123, `.env` 미수정, 끝나고 서버 종료 확인)
| 확인 | 결과 |
|---|---|
| 실제 dev/memory 서버: 띠에 데이터 소멸 안내 + 프론트 dev 줄 | 통과 |
| 띠가 상단 바와 본문 사이에 있고(높이 32px) 겹침 없음, 사이드바·화면 이름 그대로 | 통과 |
| 가짜 `/health` = firebase/firestore: 데이터 소멸 줄 없음(이 확인용 빌드는 dev 프론트라 프론트 줄과 불일치 안내만 남음) | 통과 |
| 가짜 `/health` = dev/firestore: "(dev / firestore)" 표시, 데이터 소멸이라고 말하지 않음 | 통과 |
| `/health` 연결 실패: 서버 줄 없음, 프론트 줄만, 앱 정상 | 통과 |
| 필드 없는 옛 `/health` 응답: 서버 줄 없음 | 통과 |

## 미검증
- **Firebase 프론트 빌드(`NEXT_PUBLIC_AUTH_MODE` 미설정)로 띠가 아예 안 보이는 화면**: 확인용 빌드가 dev 인증이어야 동의·진입이 되므로 브라우저로는 못 봤다. 이 경우("firestore + firebase 서버, firebase 프론트 → 아무것도 안 보임")는 순수 함수 단위 테스트로만 확인했다.
- 실제 Firebase 모드 서버(Firestore 연결)에서의 시작 로그와 `/health` 값(키 없이는 못 띄움; 코드는 환경변수 이름만 읽는다).
- 모바일 폭에서 띠 줄바꿈.
- `/health` 는 환경변수 기준이며, 서버가 이미 만든 저장소(`get_store` 캐시)와 실행 중 환경변수가 바뀌는 경우의 불일치는 보지 않는다(실행 중 환경변수 변경은 지원하지 않음).

## 열린 결정
1. 같은 터미널 창에 남은 `AUTH_MODE`/`STORE_BACKEND` 가 `--env-file` 값을 덮어쓰는 문제 자체는 지시대로 바꾸지 않았다. 대신 이제 서버 시작 로그와 화면 띠로 바로 알아볼 수 있다. 더 강하게 막으려면(예: `.env` 와 환경변수가 다르면 시작 때 경고) 별도 지시가 필요하다.
2. 띠를 `dev`/`memory` 일 때 닫을 수 있게 할지(지금은 항상 보임).

## 커밋에 포함하지 않은 것
`frontend/AGENTS.md`, `next-env.d.ts`.
