# PaceMate 작업 안내 (모든 세션이 시작할 때 읽는다)

PaceMate는 독학 학습자를 위한 AI 학습 플래너(14일 MVP)다. 이 폴더는 개발팀 세션과 검증팀(PM) 세션이 함께 쓴다. 두 세션 모두 같은 로컬 폴더를 보므로 파일을 저장하면 서로 바로 보인다.

## 역할
세션의 역할은 사용자가 정한다. 정해지지 않았으면 사용자에게 물어본다.
- 개발팀: 지정된 Phase 의 코드와 테스트를 구현한다. 설계 문서를 바꿀 때는 아래 "계약 변경" 규칙을 따른다.
- 검증팀(PM): 코드를 직접 고치지 않는다. 테스트 실행, 실제 호출 확인, 코드 읽기로 검증하고 결과와 수정 지시를 docs/ 에 문서로 남긴다. 개발팀 보고는 그대로 믿지 않고 코드와 테스트로 확인한다.
- 사용자: 두 세션 사이를 전달하고 우선순위와 다음 Phase 시작을 결정한다. Firebase, Render, Vercel 콘솔 설정과 비밀값 입력은 사용자가 직접 한다.

## 진행 원칙
- TASK.md 의 Phase 를 한 번에 하나만 진행한다. 끝나면 보고하고 멈춘다. 검증과 사용자 지시 후에만 다음 Phase 로 간다. 다음 Phase 의 뼈대나 스키마도 미리 만들지 않는다.
- TASK.md 체크박스는 직접 검증한 항목만 체크한다. 확인하지 못한 것은 "미검증"이라고 적는다.
- 현재 상태(2026-10-20): Phase 3, 4 는 검증 승인됨(dev 모드 기준). Phase 5 는 수정까지 검증팀이 확인해 승인했다(dev 모드 기준, 커밋 86a8da4). Phase 6 은 사용자 지시와 검증팀 지시서(docs/phase6_dev_prompt.md)가 나오기 전에는 시작하지 않는다. Firebase 실연동, 브라우저 화면 조작, 배포는 미검증이다. 최신 상태는 docs/ 의 phaseN_report.md, phaseN_fix_instructions.md 를 본다.
- MVP 에서 제외한 항목과 사용자 테스트 후 후보는 docs/post_mvp_backlog.md 에 있다(예: 타이머 일시정지).

## 소통 방식
- 긴 지시서와 보고서는 docs/ 에 파일로 저장하는 것이 원본이다(예: docs/phase5_dev_prompt.md, docs/phase5_report.md). 사용자가 터미널로 전달하는 글은 짧아야 한다. 긴 글을 붙여넣으면 깨지므로, 전달받은 긴 글이 끊겨 보이면 추측하지 말고 해당 파일을 직접 읽는다.
- 보고는 docs/phaseN_report.md 로 저장하고 채팅에는 한 줄 요약(완료 여부, 테스트 통과 수, 파일 경로)만 남긴다.
- 세션 사이의 메시지는 메시지함 파일로 주고받는다(복사 붙여넣기가 필요 없다). 검증팀 → 개발팀은 docs/messages/to_dev.md, 개발팀 → 검증팀은 docs/messages/to_verification.md 에 쓴다. 새 메시지는 맨 위에 추가하고(번호, 날짜, 제목, 처리 상태), 사용자는 "docs/messages/to_dev.md(또는 to_verification.md)의 최신 메시지를 읽고 처리해 주세요"만 전달한다. 긴 지시서와 보고서는 docs/ 의 별도 파일에 두고 메시지에는 경로만 적는다.
- 사용자에게는 일반 글로 설명한다. 사용자는 이 과정으로 프로젝트를 배우고 있으므로 판단 근거를 함께 설명한다.

## 기준 문서
- 제품: 서비스기획서.md, PRD.md, mission.md, mockup/index.html(표준 목업)
- 작업: TASK.md
- 설계와 결정: docs/phase1_design.md, docs/erd_current.md, docs/phase3_auth.md, docs/phase4_plan.md
- 사용자용 가이드: docs/firebase_setup_guide.md

## 핵심 결정 (바꾸지 않는다. 바꾸려면 사용자 승인)
- UID 는 Firebase ID 토큰에서만 정한다. 요청 본문의 user_id 나 소유 정보를 믿지 않는다. 개인 데이터 API 는 require_consented_uid 를 쓴다. 오류는 ErrorResponse 형식이다.
- 동의 전에는 익명 UID 와 개인 데이터를 만들지 않는다.
- 수준(level)은 서술형 라벨이다. 번호(order)는 같은 과정 안의 순서 등급일 뿐이며 점수나 간격 계산, 비교에 쓰지 않고 화면에도 표시하지 않는다. 진행률은 완료 과제 수 / 전체 과제 수다.
- 계획은 확정할 때만 저장한다(POST /api/plan/confirm 이 목표와 과제를 함께 저장). 초안 생성은 저장하지 않는다.
- 추천 요일은 마감일이 아니다. 놓쳐도 연체, 실패, 자동 이월 처리를 하지 않는다.
- 날짜와 주간 경계(월~일)는 서비스 시간대 Asia/Seoul 이다. 백엔드는 backend/clock.py, 프론트는 frontend/lib/week.ts 만 쓴다. date.today(), 브라우저 로컬 날짜, toISOString 날짜 변환을 쓰지 않는다.
- 쓰기 요청은 client_request_id 로 멱등 처리한다.
- AI 결과는 서버가 스키마와 규칙으로 검증한다. 규칙을 어기면 조용히 고치지 않고 거부하고 재시도한다. 로그에 사용자 입력 원문, 회고, AI 응답 원문, 토큰을 남기지 않는다.
- 참고자료는 팀이 검토한 backend/data/rag_documents.json 만 쓴다. 자료가 없는 분야에서 근거가 있는 것처럼 표시하지 않는다.
- 구현 이름 기준: field, course, target_date, current_level_order 등 코드의 이름이 기준이다.
- 계약 변경: DTO 를 바꾸면 backend/schemas.py, docs/erd_current.md, docs/phase1_design.md, 프론트 타입을 함께 갱신한다.

## 비밀값
- OPENAI_API_KEY, FIREBASE_SERVICE_ACCOUNT_JSON 등은 backend/.env, frontend/.env.local 에만 둔다(.gitignore 에 제외됨). 코드, 문서, 로그, 채팅, 커밋에 쓰지 않는다.
- 값이 설정됐는지는 값을 출력하지 않고 확인한다(예: grep -c).
- 로컬은 AUTH_MODE=dev, STORE_BACKEND=memory 로 키 없이 개발한다. 배포(Render)에서는 이 값들을 거부한다.

## 실행과 테스트
- 백엔드: backend 폴더에서 python -m uvicorn main:app --reload --port 8001 --env-file .env
- 백엔드 테스트: backend 폴더에서 python -m pytest
- 프론트: frontend 폴더에서 npm run dev, npm run typecheck, npm test, npm run build
- 실제 OpenAI 호출 확인은 필요한 만큼만(비용). 이미 떠 있는 서버를 건드리지 말고 빈 포트에 따로 띄운 뒤 끝나면 종료한다.

## Git
- 로컬 작업과 커밋은 자유롭게 하고, origin/main 에 push 해도 된다. 조건: 테스트 통과, 비밀값과 개인 파일 없음, 의도한 파일만 포함.
- 강제 push(--force)와 다른 브랜치·저장소로의 push 는 사용자에게 먼저 확인한다.
- 올리지 않는 것: .env 류, 대화기록.md(개인 메모), 브라우저에서 저장한 PDF, reference-AI NATIVE M -2/ 폴더.

## 아키텍처 한눈에
- 프론트: Next.js(Vercel 예정), 백엔드: FastAPI(Render 예정), 인증과 DB: Firebase Authentication(익명)과 Firestore, AI: OpenAI API(백엔드에서만 호출).
- 모든 Firebase 값은 같은 Firebase 프로젝트에서 나와야 한다.
