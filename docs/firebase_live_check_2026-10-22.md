# Firebase 실연동 확인과 모드 전환 기록 (검증/PM 세션, 2026-10-22)

이전 검증팀 세션이 끊긴 뒤 새 세션에서 한 일이다. 값(키, 토큰, 서비스 계정 내용)은 이 문서에 쓰지 않는다.

## 1. 한 일

1. **backend/.env 의 서비스 계정 JSON 수정(사용자가 직접).** 닫는 `}` 가 줄바꿈되어 9번 줄에 떨어져 있어 JSON 이 깨져 있었다. 8번 줄 끝에 붙인 뒤 파싱이 성공했다.
2. **키 점검(값 출력 없음).** JSON type=service_account, project_id, private_key_id, private_key(PEM 형식), client_email, token_uri 존재. 백엔드 project_id 가 frontend/.env.local 의 NEXT_PUBLIC_FIREBASE_PROJECT_ID 와 일치한다.
3. **실제 Firebase 호출 확인.** 빈 포트 8200 에 firebase/firestore 모드로 서버를 따로 띄우고(.env 는 바꾸지 않고 프로세스 환경변수로만 덮어씀), 익명 사용자 2명을 만들어 확인한 뒤 서버와 테스트 사용자를 삭제했다.
4. **모드 전환(사용자 승인 "둘 다 진행").** backend/.env: AUTH_MODE=firebase, STORE_BACKEND=firestore. frontend/.env.local: NEXT_PUBLIC_AUTH_MODE=firebase.
5. **서버 정리와 재시작.** 이전 세션이 남긴 8003~8006 백엔드 4개(프로세스 8개)를 종료하고, 8001 백엔드와 3000 프론트를 새로 띄웠다. 두 서버 모두 응답 200.

## 2. 실연동 검증 결과 (백엔드 API 기준)

| 항목 | 결과 |
|---|---|
| 토큰 없음, 잘못된 토큰 | 401 |
| 익명 로그인(콘솔에서 켜져 있음) | 성공, 두 사용자 UID 서로 다름 |
| 동의 전 개인 데이터 접근 | 403 |
| 동의 저장, 목표 저장(Firestore) | 201, 201 |
| 타 UID 격리 | B 의 목록 0건, A 의 목표 조회와 삭제 403 |
| 본인 목표 조회 | 200 |
| 데이터 삭제(delete-data) | 200, 이후 403 CONSENT_REQUIRED(데이터와 동의 기록 삭제) |

처음 한 번 "삭제 후 목표 1개"로 보인 것은 검증 스크립트가 오류 본문의 키 개수를 목표 개수로 센 실수였다. 서버 동작은 정상이다.

## 3. 미검증

- 브라우저 화면 조작과 프론트의 Firebase 익명 로그인 연결(NEXT_PUBLIC_AUTH_MODE=firebase 상태의 화면 흐름).
- Firebase 콘솔에서 Authentication 사용자와 Firestore 문서(users, consent_records, goals)가 보이는지.
- 개발팀 phase5b_fix_report_2.md 는 이 시점에 없었다. Phase 5B 수정 2번(docs/phase5b_fix_instructions_2.md)의 코드 검증은 하지 않았다.
- 사용자가 직전 검증팀 세션에 전달한 화면 테스트 결과는 이 세션에 없다.

## 4. 주의

- 지금 .env 가 firebase 모드라서 로컬 실행도 실제 Firebase 에 데이터를 쓴다. 개발팀이 키 없이 개발하려면 dev/memory 로 되돌려야 한다(CLAUDE.md 의 로컬 기본값).
- uvicorn 은 시스템 Python 에 없다. backend/.venv 의 python 을 쓴다.
- 현재 미커밋: docs/phase5b_report.md(빈 줄 삭제), frontend/next-env.d.ts(Next 가 dev 실행 때 자동 수정), frontend/AGENTS.md(Next 가 자동 생성). 앞의 둘은 커밋하지 않는다.

## 5. 서버 실행 명령(VS Code 터미널)

백엔드(터미널 1, backend 폴더):
```
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8001 --env-file .env
```
프론트(터미널 2, frontend 폴더):
```
cd frontend
npm run dev
```
이미 떠 있으면 "포트 사용 중" 오류가 난다. 먼저 종료한다.
```
Get-NetTCPConnection -LocalPort 8001,3000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

## 6. 세션 중단 관련 조사 요약(공식 문서, code.claude.com/docs/en/ sessions, agent-view, context-window, claude-directory)

- 이번 중단의 원인을 특정하는 문서는 없다.
- 컨텍스트가 차면 새 세션이 아니라 같은 세션에서 자동 압축된다.
- 백그라운드 세션은 끝났거나 입력 대기 후 약 1시간 연결이 없으면 정지한다. 기록은 남고 다시 붙으면 이어진다. Ctrl+T 로 고정하면 막을 수 있다. 기기 종료 시에도 멈춘다.
- `/resume` 은 대화 기록, 모델, 권한 모드를 복원하고, 실행 중이던 프로세스와 서버는 복원하지 않는다. 파일은 되돌리지 않는다.
- 기록은 `%USERPROFILE%\.claude\projects\<프로젝트>\<세션ID>.jsonl`, 기본 30일 보존(cleanupPeriodDays).
- 같은 폴더에서 세션이 여럿이면 `claude --resume` 목록에서 고르거나 `claude -n <이름>` 으로 이름을 붙여 `claude --resume <이름>` 으로 연다.
