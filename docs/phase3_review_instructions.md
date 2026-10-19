# Phase 3 검증 결과 — 개발팀 수정 지시서

작성: 검증팀. 이 문서는 표 없이 목록으로만 작성했다.
참고: 데이터 구조는 docs/erd_current.md 를 본다.

전제: Phase 4는 사용자 지시 전까지 시작하지 않는다. 아래는 Phase 3 범위의 수정과 Phase 4 착수 전 계약 정리다. 수정 후 테스트 결과를 보고한다.

---

## 0. 수준(level) 설계 원칙 (공통 기준)

- 수준은 서술형 라벨이다. 이름과 설명 텍스트가 의미를 가지며, AI가 사람처럼 해석해 인사이트에 쓴다. 정량 지표나 표준 등급이 아니다.
- 수준 번호는 같은 과정 안의 순서 등급이다(높을수록 상위). 간격 계산, 비율, 평균, 합산, 다른 과정이나 다른 사용자와의 비교에 쓰지 않는다.
- 수준표는 별도 테이블에 저장하지 않는다(의도된 설계).
- 진행률은 수준이 아니라 완료 과제 수 / 전체 과제 수로 계산한다.
- 화면에는 번호를 표시하지 않고 수준 이름만 표시한다(PRD FR-02).

---

## 1. 필수 수정 (Phase 4 착수 전, 계약·설계)

### 1-1. 수준 DTO를 과정별로 바꾼다
- 파일: backend/schemas.py
- 현재: PathRecommendationResponse 에 courses 목록과 levels 목록이 따로 있다. 모든 과정이 같은 수준표를 쓰게 된다.
- 수정: 평면 levels 를 없애고, 각 과정(CourseItem) 안에 levels 목록을 둔다. 수준 항목에는 순서값, 이름, 설명을 둔다.
- 결정 요청: LevelItem.level 이 ge=1, le=5 로 고정되어 있다. PRD는 개수를 정하지 않았다. 5단계 고정을 유지할지 풀지 정해서 보고한다.

### 1-2. 목표 수준 검증을 강화한다
- 파일: backend/main.py 의 _validate_goal, backend/schemas.py 의 PlanGenerateRequest.target_level 설명
- 현재: target_level_num < current_level_num 일 때만 거부한다. 같은 수준(현재=3, 목표=3)이 201로 저장된다. DTO 설명도 "current_level 이상"이다.
- 수정: target_level_num <= current_level_num 이면 400으로 거부한다. DTO 설명을 "current_level 보다 큰 값"으로 고친다.
- 근거: PRD FR-02 "목표는 현재 수준보다 뒤에 있는 수준만 선택할 수 있다".
- 테스트: 같은 수준 거부, 낮은 수준 거부, 높은 수준 허용.

### 1-3. 수준 설명도 목표에 저장한다
- 파일: backend/schemas.py (GoalCreateRequest, GoalUpdateRequest, GoalResponse), backend/main.py
- 현재: goals 에는 current_level_name, target_level_name 만 저장되고 설명은 저장되지 않는다.
- 수정: 선택한 현재 수준과 목표 수준의 설명(예: current_level_description, target_level_description)을 선택 필드로 추가해 스냅샷으로 저장한다. 수준표 전체는 저장하지 않는다.
- 목적: 튜터와 인사이트 프롬프트가 수준을 해석할 재료로 쓴다.

### 1-4. 계약 누락을 보완한다
- 파일: backend/schemas.py
- PathRecommendationRequest 에 학습 목표를 받는 필드를 추가한다(TASK 4.1 "분야·목표 자유 입력"). 지금은 선택 필드인 user_context 뿐이다.
- PathRecommendationResponse 에 직무명 추천 목록(최대 5개)을 추가한다(TASK 4.2).
- PlanGenerateRequest 에 직무명 선택값과 goal_id 를 추가한다.
- selected_courses(목록)와 GoalCreateRequest.course(단일 문자열)가 맞지 않는다. 한 목표에 과정 1개인지 여러 개인지 정해서 하나로 통일한다.
- WeeklyTaskPlanItem.week_number 는 PRD 계획 데이터에 없으므로 제거한다.
- WeeklyTaskPlanItem.suggested_weekday 의 타입을 str 에서 Weekday 리터럴로 맞춘다.

### 1-5. 필드명을 확정한다
- 현재 current_level_num, target_level_num 은 점수처럼 읽힌다. current_level_order, target_level_order 또는 _rank 로 바꿀지 결정한다. 어느 쪽이든 문서와 DTO 설명에 "순서 등급, 계산에 쓰지 않음"을 적는다.
- PRD 6장의 이름(domain, due_date, selected_process, 회고 text)과 구현 이름(field, target_date, course, content) 중 어느 쪽을 기준으로 할지 정한다. 한쪽 문서를 맞춘다.

### 1-6. 타이머 시각 필드를 확정한다
- 파일: backend/schemas.py 의 StudyLog 관련 DTO, docs/erd_current.md
- 현재: study_logs 에 study_date, minutes, activity 만 있다.
- PRD FR-03 과 6장은 started_at, ended_at (그리고 studied_at)을 요구한다. 선택 필드로 추가할지 Phase 5 시작 전에 확정한다.

---

## 2. Phase 3 코드 수정

### 2-1. 동의 없이 새 UID가 만들어지는 경로를 막는다
- 파일: frontend/components/AuthProvider.tsx 의 초기화 useEffect
- 현재: localStorage 에 동의 표시가 있고 Firebase 세션이 없으면(예: IndexedDB 삭제), 모달 없이 startAnonymousSession() 과 recordConsent() 를 실행한다. 새 UID에 동의가 자동 기록된다.
- 수정: restoreSession() 이 null 이면 startAnonymousSession() 을 호출하지 않고 clearConsent() 후 status 를 needs-consent 로 보낸다.
- 근거: PRD FR-01 "동의 후 익명 UID 발급".

### 2-2. 미구현 API에도 인증을 적용하고 오류 형식을 통일한다
- 파일: backend/main.py
- 대상: /api/study-logs 4개, /api/data/summary, /api/dashboard/summary, /api/conversations 4개, /api/resources
- 현재: 토큰 없이 호출해도 401이 아니라 501이 오고, 본문이 {"detail": "문자열"} 이다. 프론트 apiRequest 는 detail 이 객체가 아니면 INTERNAL_ERROR 로 처리한다.
- 수정: 개인 데이터 엔드포인트는 Depends(require_consented_uid) 를 적용한다. 501 응답은 api_error(501, "NOT_IMPLEMENTED", 메시지) 로 ErrorResponse 형식에 맞춘다.
- 결정 요청: /api/resources 를 공개로 둘지 인증을 요구할지 정해서 문서에 적는다.

### 2-3. 데이터 삭제 실패 처리를 구분한다
- 파일: backend/main.py 의 delete_user_data, backend/auth.py 의 delete_auth_user
- 현재: Firestore 삭제 후 delete_auth_user 를 호출하는데 UserNotFoundError 만 처리한다. 그 밖의 Firebase 오류는 500이 된다. 이때 데이터는 이미 삭제된 상태다. 사용자는 실패로 보고 재시도한다.
- 수정: Auth 삭제 실패를 따로 잡아, 데이터 삭제는 성공했고 계정 정리만 재시도가 필요하다는 응답(예: 코드 AUTH_CLEANUP_PENDING, 200 또는 207)으로 구분한다. 프론트는 이 경우에도 clearConsent() 와 세션 정리를 진행한다.
- 오류 메시지·토큰·회고 원문은 로그에 남기지 않는다.

### 2-4. 동의 기록을 멱등하게 만든다
- 파일: backend/main.py 의 create_consent
- 현재: 호출할 때마다 consent_records 가 새로 생긴다(같은 UID 2번 호출 시 2건 재현됨).
- 수정: 같은 user_id 와 같은 terms_version 의 기록이 이미 있으면 새로 만들지 않고 기존 기록을 반환한다(상태 코드는 200 또는 201 유지 중 택일해서 문서화). 버전이 바뀌면 새 기록을 만든다.
- 테스트: 같은 버전 2회 호출 시 기록 1건, 버전 변경 시 2건.

### 2-5. 도메인 검증을 추가한다
- 파일: backend/main.py (_validate_goal, create_task), backend/schemas.py
- target_date 가 오늘 이전이면 400으로 거부한다.
- field, course, title 이 공백만 있는 문자열이면 거부한다(공백 제거 후 길이 검사).
- Phase 4에서 POST /api/tasks 에도 주간 예상 시간 총량(weekly_hours 기준)과 target_date 초과 주간 검증을 적용한다(PRD FR-02 수용 기준). AI를 거치지 않고 저장하는 경로가 되므로 반드시 같은 규칙을 쓴다.

### 2-6. 배포 안전장치를 보강한다
- 파일: backend/auth.py 의 assert_safe_auth_config, backend/store.py, backend/.env.example
- 현재: AUTH_MODE=dev 는 RENDER 환경변수가 있을 때만 막는다. STORE_BACKEND=memory 는 막지 않는다. .env.example 기본값이 dev, memory 다.
- 수정: 배포 환경(RENDER 설정됨)에서 STORE_BACKEND=memory 도 기동 시 RuntimeError 로 거부한다. .env.example 에 "로컬 전용, 배포 사용 금지" 경고 주석을 추가한다.

---

## 3. 개선 권장 (여유 시)

- 읽기 비용: require_consented_uid 가 요청마다 users 문서를 읽는다. 같은 요청 안에서 재사용하고(get_profile, create_goal 도 users 를 다시 읽음), 캐시나 토큰 클레임 활용을 검토한다.
- 삭제 N+1: delete_goal 이 과제마다 delete_where 를 2번씩 실행한다. goal_id 기준으로 한 번에 조회하고 배치 삭제로 줄인다.
- 프론트 요청: apiRequest 에 타임아웃과 재시도를 추가한다. 초기화 오류(status error)가 동의 모달로 보이지 않게 전용 오류·재시도 화면을 둔다.
- 재현성: requirements.txt 와 프론트 의존성 버전을 고정한다. 루트와 backend 의 pytest.ini 를 하나로 정리한다.
- 저장소 위생: 대화기록.md 는 커밋하지 않는다. 내용에 비밀값이나 개인정보가 없는지 확인하고, 커밋 대상이 아니면 .gitignore 에 추가한다.

---

## 4. 인사이트·튜터 구현 원칙 (Phase 5~6 대비)

- 인사이트의 근거는 사용자의 실제 학습 기록과 회고다. 수준 설명은 배경 맥락으로만 쓴다.
- 수준을 판정해서 단정하지 않고 제안 형태로 말한다.
- 기록이 부족하면 분석하지 않고 기록을 더 남기라고 안내한다.
- 진행률, 학습 시간, 완료 수 같은 숫자는 서버가 계산하고, 해석과 조언만 AI가 맡는다.
- 모든 AI 결과에 생성 안내를 표시한다.

---

## 5. 검증 요청

- Firebase 실연동(Task 0.5)은 아직 검증되지 않았다. 완료 후 인증, Firestore 보안 규칙, 인덱스를 재검증한다. Phase 3의 3.2, 3.4, 3.5는 dev 모드 기준으로만 확인된 상태다.
- firebase 모드의 verify_id_token 분기(만료, 위조, 인증서 조회 실패)를 모킹한 단위 테스트를 추가한다.
- 위 수정마다 테스트를 추가한다. 특히 1-2(같은 수준 거부), 2-1(동의 흐름), 2-4(멱등성)를 포함한다.
- 수정 후 pytest 전체 결과와 프론트 typecheck, build 결과를 보고한다.
