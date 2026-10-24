# 운영 수정 지시 — 실행 모드(dev/Firebase, 메모리/Firestore) 가시화 (PM, 2026-10-25)

대상: 현재 main. 끝나면 docs/ops_fix_report_mode_visibility.md 로 보고하고 멈춘다. Phase 7 은 시작하지 않는다. 작은 수정이다.

## 1. 왜 하는가 (실제 사고)
사용자가 Firebase 모드로 테스트하려 했지만 서버가 계속 dev 모드(메모리 저장)로 떠 있어, 서버를 껐다 켜면 데이터가 사라지는 일이 반복됐다(2026-10-23, 2026-10-25). 사용자는 어떤 모드인지 알 방법이 없었고(서버 시작 로그에도, `/health` 에도, 화면에도 표시가 없다), Firebase 콘솔의 사용량 그래프를 데이터 저장으로 오해했다. PM 이 확인한 단서: 목표 id 형식(32자리 16진수 = 메모리), 가짜 dev 토큰으로 조회했을 때 401 이 아니라 403(= dev 인증이 켜져 있음). 사용자가 보낸 Firebase 콘솔 캡처(2026-10-25)로 확정: Firestore 에는 컬렉션 consent_records, goals, study_logs, tasks, users 만 있고 consent_records 문서는 **1건(consented_at 2026-10-22, 약관 v1.0)** 뿐이다. 사용량 그래프의 쓰기 29건도 10/22 하루뿐이며 그 이후 쓰기가 없다(conversations, insights, feedback 컬렉션도 없음, 약관 v1.1 동의 기록 없음). 즉 10/22 라이브 확인(docs/firebase_live_check_2026-10-22.md) 이후의 테스트 데이터는 모두 메모리에만 저장됐다. 원인은 같은 터미널 창에 남은 환경변수(`AUTH_MODE=dev`, `STORE_BACKEND=memory`)로 추정되며(PC 영구 환경변수와 PowerShell 프로필에는 없음 확인), 사용자가 눈으로 보고 판단할 수 있어야 재발을 막는다.

## 2. 만드는 것
1. **서버 시작 로그 한 줄:** 앱이 뜰 때 `INFO startup auth_mode=<dev|firebase> store_backend=<memory|firestore>` 한 줄을 남긴다(값은 모드 이름뿐, 비밀값·URL·프로젝트 ID 없음). dev 또는 memory 이면 한 줄 더 `WARNING data is NOT persisted: store_backend=memory (data disappears when the server stops)` 를 남긴다.
2. **`GET /health` 확장:** 기존 `{status, service}` 에 `auth_mode`, `store_backend` 를 추가한다(비밀값 없음, 인증 불필요). 배포 환경(`RENDER` 설정)에서도 같은 값이 나온다(배포에서는 memory/dev 가 거부되므로 항상 firestore/firebase).
3. **화면 배너(프론트):** 앱이 뜰 때 `/health` 를 한 번 읽어 `store_backend === "memory"` 이거나 `auth_mode === "dev"` 이면 상단 바 근처에 **눈에 띄지만 가벼운 안내 띠**를 보인다: "개발 모드예요. 서버를 끄면 데이터가 사라져요." (모드 이름 병기: `dev / memory`). Firebase/Firestore 이면 아무것도 보이지 않는다. `/health` 를 읽지 못하면(서버 연결 실패) 배너 대신 기존 오류 처리. 프론트 쪽 `NEXT_PUBLIC_AUTH_MODE=dev` 이면 서버 값과 무관하게 "프론트가 dev 인증 모드예요" 를 같은 띠에 함께 표시한다(프론트·서버 모드 불일치 진단용).
4. 목업과의 관계: 이 띠는 개발·검증용 안내이며 목업에 없다. 5C 의 앱 셸과 스타일 토큰을 재사용하고 레이아웃을 흔들지 않는다(보고서에 "구현에만 있음(의도적)"으로 적는다).

## 3. 하지 않는 것
인증·저장소 동작 변경, 모드 자동 전환, 기존 환경변수 규칙 변경(`--env-file` 이 이미 설정된 환경변수를 덮어쓰지 않는 것은 그대로), 배포 설정.

## 4. 테스트
- backend: `/health` 응답에 `auth_mode`, `store_backend` 포함(dev/memory 와 firebase/firestore 조합을 환경변수로 바꿔 확인), 시작 로그 형식(`caplog`), 로그와 응답에 비밀값·URL·UID 없음. 기존 756건 통과.
- frontend: 배너 표시 조건 순수 함수 단위 테스트(memory, dev, firestore+firebase, `/health` 실패, 프론트 dev). typecheck, test, build.
- 실제 서버 확인(빈 포트, `AUTH_MODE=dev STORE_BACKEND=memory` 환경변수 덮어쓰기, `.env` 수정 금지, 끝나면 종료): 배너가 보이는지, Firebase 모드 값으로는 보이지 않는지 가짜 `/health` 응답으로 확인하고 못 한 것은 "미검증"으로 적는다.

## 5. 보고서
변경 요약, 테스트 건수, 화면 변경(배너 문구와 위치 캡처 설명), 미검증, 열린 결정.

