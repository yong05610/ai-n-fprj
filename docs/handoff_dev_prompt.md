# 개발팀 인수인계 프롬프트 (새 세션용)

너는 PaceMate 개발팀의 새 세션이다. 이전 개발팀 세션이 길어져 새로 시작한다. 아래를 순서대로 읽고 이어서 작업한다.

## 1. 먼저 읽을 것 (순서대로)
1. CLAUDE.md (프로젝트 규칙, 핵심 결정, 소통 방식, Git 규칙)
2. TASK.md (Phase 별 작업과 체크 상태), PRD.md 의 FR-02, FR-03, FR-06, 서비스기획서.md
3. docs/phase5_report.md (이전 개발팀의 Phase 5 구현 보고)
4. docs/phase5_fix_instructions.md (검증팀의 수정 지시. 지금 해야 할 일의 원본)
5. docs/erd_current.md, docs/phase1_design.md, docs/phase4_plan.md (데이터 구조와 계약)
6. docs/post_mvp_backlog.md (MVP 에서 제외하기로 한 항목)

## 2. 지금 해야 할 일
docs/phase5_fix_instructions.md 의 항목을 수정한다: P5-1, P5-2, P5-3, P5-4 는 필수, P5-5, P5-6, P5-7 은 권장 또는 문서화, 사소한 사항 포함. 타이머 일시정지는 사용자 결정으로 이번에 구현하지 않는다(해당 지시서 절 참고).

중요: 작업 폴더에 이미 커밋되지 않은 수정이 있을 수 있다. 이전 개발팀 세션이 수정 중이었을 가능성이 크다. 시작 전에 git status 와 git diff 로 무엇이 바뀌었는지 확인하고, 이미 반영된 항목은 다시 하지 말고 이어서 완성한다. 확인 없이 되돌리거나 덮어쓰지 않는다.

수정이 끝나면:
- docs/phase5_fix_report.md 에 보고서를 저장한다(항목별 결과, 변경 파일, 테스트 출력, P5-1 과 P5-2 를 실제 서버 HTTP 로 다시 확인한 전후 결과, 사용자가 눌러 볼 시나리오, 미검증 항목).
- 채팅에는 한 줄 요약(완료 여부, 테스트 통과 수, 파일 경로)만 남기고 멈춘다.
- 다음 Phase(Phase 6)는 검증팀 승인과 사용자 지시가 있기 전에 시작하지 않는다.

## 3. 현재 상태
- Phase 0~2: 완료(사용자 몫 항목은 TASK.md 참고). Phase 3, 4: 검증 승인됨(dev 모드 기준, Phase 4 는 실제 OpenAI 호출까지 확인).
- Phase 5: 구현 보고 후 검증에서 결함이 발견되어 수정 중이다.
- 테스트 기준선: backend pytest 174건(Phase 5 보고 시점), frontend typecheck, npm test 6건, build 통과.
- 미검증: Firebase 실연동(사용자가 콘솔 설정 중), 브라우저 화면 직접 조작, 배포.

## 4. 이 프로젝트에서 지켜온 규칙 (요약, 자세한 것은 CLAUDE.md)
- 한 번에 한 Phase 만 한다. 끝나면 보고하고 멈춘다.
- 확인하지 못한 것은 체크하지 말고 "미검증"이라고 적는다. 실제 HTTP 로 확인했는지, 가짜 AI 로만 확인했는지를 구분해 쓴다.
- 비밀값(OpenAI 키, Firebase 서비스 계정)은 코드, 로그, 문서, 채팅, 커밋에 쓰지 않는다. 값은 출력하지 않고 존재만 확인한다.
- 날짜는 backend/clock.py 와 frontend/lib/week.ts 만 쓴다(Asia/Seoul). 수준 번호는 순서일 뿐 계산에 쓰지 않는다. UID 는 토큰에서만 정한다.
- 쓰기 요청은 client_request_id 로 멱등 처리한다.
- 설계나 계약을 바꾸면 schemas.py, docs/erd_current.md, docs/phase1_design.md, 프론트 타입을 함께 갱신한다.
- 긴 보고는 파일로 쓰고, 채팅에는 짧은 요약만 쓴다(터미널 복사 붙여넣기에서 긴 글이 깨진다).
- origin/main 에 push 해도 된다(테스트 통과, 비밀값 없음, 의도한 파일만). 강제 push 는 사용자에게 먼저 확인한다. 이전 개발팀이 쓴 파일과 검증팀 파일을 섞어서 덮어쓰지 않는다.

## 5. 검증팀이 지금까지 잡아낸 결함의 유형 (같은 실수를 피한다)
- 멱등 처리의 순서: 활성 상태 확인이 멱등 키 확인보다 먼저라서, 응답을 못 받고 재시도하면 오류가 났다. 멱등 키 조회를 먼저 한다.
- 삭제 전파 누락: 목표 삭제가 활성 타이머를 정리하지 않았다. 부모를 삭제하는 모든 경로에서 자식과 파생 상태를 정리했는지 점검한다.
- 화면 집계 불일치: 토글 후 다른 위젯의 수치를 다시 불러오지 않았다. 변경 후 관련 집계를 모두 갱신한다.
- 가짜 AI 로만 통과: 실제 모델은 규칙(시간 한도, 수준 개수)을 지키지 않을 수 있다. AI 관련 변경은 가능하면 실제 키로 소수 호출해 확인한다.
- 부분 문자열 매칭, UTC 와 KST 날짜 혼용, 일반어 오매칭 같은 데이터 처리 실수.
- 이미 커밋된 원본 데이터 파일을 실수로 덮어쓴 적이 있다(backend/data/rag_documents.json). 데이터 파일은 읽기 전용으로 다룬다.

## 6. 실행 방법
- 백엔드: backend 폴더에서 python -m uvicorn main:app --reload --port 8001 --env-file .env
- 백엔드 테스트: backend 폴더에서 python -m pytest
- 프론트: frontend 폴더에서 npm run dev, npm run typecheck, npm test, npm run build
- 실제 서버 확인은 이미 떠 있는 서버를 건드리지 말고 빈 포트에 따로 띄우고 끝나면 종료한다. Windows 콘솔에서 한글 출력이 깨지면 PYTHONIOENCODING=utf-8 로 실행한다.
