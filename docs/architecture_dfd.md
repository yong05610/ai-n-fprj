# PaceMate 시스템 구조도와 DFD (PM 정리, 2026-10-25)

기준: 배포된 현재 main(Phase 7 + 배포 후 수정). 근거: `backend/main.py` 의 실제 라우트(코드에서 추출), `backend/store.py`, `backend/*.py` 모듈 구성, `docs/erd_current.md`, `docs/deploy_guide.md`. 데이터 구조(ERD)는 `docs/erd_current.md`. 화면의 그림은 Mermaid 로 작성했다(GitHub, VS Code 미리보기에서 보인다).
주의: 라우트와 저장소는 코드로 확인했고, 프로세스별 "어떤 컬렉션을 읽고 쓰는가"는 ERD 와 라우트 이름에서 정리한 것이다(함수 단위로 전수 확인하지는 않았다).

## 1. 시스템 구성도 (배포 구조)

```mermaid
flowchart LR
    U["학습자·관리자<br/>브라우저"]
    subgraph V["Vercel (프론트엔드, Next.js)"]
        FE["화면 8개 + 관리자 2개<br/>ServerGate(서버 깨우기)<br/>lib/api.ts (GET 재시도)"]
    end
    subgraph R["Render 무료 (백엔드, FastAPI)"]
        BE["main.py 라우트<br/>인증·동의 검사<br/>AI 결과 검증<br/>schedule.py·clock.py"]
    end
    subgraph G["Google Firebase"]
        FA["Authentication<br/>(익명 로그인)"]
        FS["Firestore<br/>(사용자 데이터)"]
    end
    OA["OpenAI API"]
    RAG["검토된 자료<br/>rag_documents.json<br/>resources_catalog.py"]

    U -->|"HTTPS 접속"| FE
    U -->|"익명 로그인, ID 토큰 발급"| FA
    FE -->|"API 요청 + ID 토큰<br/>(CORS: 프론트 주소만 허용)"| BE
    BE -->|"토큰 검증, UID 확인"| FA
    BE -->|"읽기·쓰기(서비스 계정)"| FS
    BE -->|"AI 호출(키는 서버에만)"| OA
    BE -->|"읽기 전용"| RAG
```

핵심: 브라우저는 OpenAI 와 Firestore 에 직접 가지 않는다. 모든 데이터와 AI 요청은 백엔드를 거치고, 백엔드는 **토큰에서 UID 를 정한다**. 비밀값(OpenAI 키, Firebase 서비스 계정)은 Render 환경변수에만 있다.

## 2. 백엔드 모듈 구조

```mermaid
flowchart TB
    M["main.py<br/>라우트·인증 의존성·요청 처리"]
    A["auth.py<br/>토큰 검증, 모드 검사(dev/firebase)"]
    D["deploy_config.py<br/>배포 환경 시작 검사"]
    ST["store.py<br/>저장소(memory / Firestore)"]
    SC["schemas.py<br/>요청·응답 DTO"]
    AS["ai_schemas.py<br/>AI 출력 스키마"]
    AC["ai_client.py<br/>OpenAI 호출·재시도"]
    P["prompts.py<br/>프롬프트"]
    SH["schedule.py<br/>주차 타임라인 계산"]
    CK["clock.py<br/>Asia/Seoul 날짜·주"]
    IR["insight_rules.py<br/>인사이트 충분/부족 규칙"]
    T["tutor.py<br/>튜터 답변 검증·출처"]
    RG["rag.py<br/>자료 검색"]
    RC["resources_catalog.py<br/>자료 카탈로그"]
    E["errors.py<br/>ErrorResponse 형식"]

    M --> A
    M --> D
    M --> ST
    M --> SC
    M --> AC
    M --> SH
    M --> CK
    M --> IR
    M --> T
    M --> RG
    M --> RC
    M --> E
    AC --> P
    AC --> AS
    T --> RG
```

## 3. DFD

범례: 사각형 = 외부 개체, 둥근 사각형 = 프로세스, 원통 = 데이터 저장소.

### 3-1. 레벨 0 (컨텍스트)

```mermaid
flowchart LR
    L["학습자"]
    AD["관리자<br/>(ADMIN_UIDS)"]
    FB["Firebase<br/>Authentication"]
    OAI["OpenAI"]
    SYS(("PaceMate<br/>시스템"))
    DOC[("검토된 학습 자료<br/>읽기 전용")]

    L -->|"동의, 학습 목표·기록·회고, 질문, 피드백, 삭제 요청"| SYS
    SYS -->|"계획 초안, 진행 현황, 인사이트, 튜터 답변, 참고자료"| L
    AD -->|"사용자·피드백 조회·상태 변경"| SYS
    SYS -->|"집계된 사용자 현황, 피드백 목록"| AD
    SYS <-->|"ID 토큰 / UID 확인"| FB
    SYS -->|"학습 분야·질문 등 AI 입력"| OAI
    OAI -->|"AI 생성 결과"| SYS
    DOC -->|"자료·출처"| SYS
```

### 3-2. 레벨 1 개요 (프로세스와 저장소, 외부 개체는 묶어서 표시)

```mermaid
flowchart TB
    L["학습자"]
    AD["관리자"]
    FB["Firebase Auth"]
    OAI["OpenAI"]

    P1("P1 인증·동의<br/>/api/consent, /api/user/profile")
    P2("P2 학습 경로·계획<br/>/api/path/ideas, /api/path/recommend<br/>/api/plan/generate, /api/plan/confirm")
    P3("P3 학습 실행·기록<br/>/api/tasks, /api/timer/*<br/>/api/study-logs")
    P4("P4 대시보드·분석<br/>/api/dashboard/summary<br/>/api/analytics/overview, /api/data/summary")
    P5("P5 AI 인사이트<br/>/api/goals/id/insight")
    P6("P6 AI 튜터·참고자료<br/>/api/conversations(/id/messages)<br/>/api/goals/id/references, /api/resources")
    P7("P7 피드백·관리자<br/>/api/feedback, /api/admin/*")
    P8("P8 데이터 삭제<br/>/api/user/delete-data")

    D1[("users<br/>consent_records")]
    D2[("goals")]
    D3[("tasks")]
    D4[("study_logs<br/>reflections")]
    D5[("conversations")]
    D6[("insights")]
    D7[("feedback")]
    D8[("learning documents<br/>(읽기 전용 파일)")]

    L -->|"약관 동의"| P1
    L -->|"분야·수준·기간·주당 시간"| P2
    P2 -->|"초안(저장 안 함)"| L
    L -->|"과제 완료, 타이머, 기록, 회고"| P3
    L --> P4
    P4 --> L
    L -->|"인사이트 요청"| P5
    L -->|"질문"| P6
    P6 -->|"답변+출처"| L
    L -->|"피드백, 삭제 요청"| P7
    L --> P8
    AD --> P7
    P7 --> AD

    P1 <-->|"토큰 검증"| FB
    P1 --> D1
    P2 <-->|"직무 예시·과정·계획 초안"| OAI
    P2 -->|"확정 때만 저장"| D2
    P2 --> D3
    P3 --> D3
    P3 --> D4
    P3 -->|"활성 타이머"| D1
    D2 --> P4
    D3 --> P4
    D4 --> P4
    D6 --> P4
    D3 --> P5
    D4 --> P5
    P5 <-->|"인사이트 생성"| OAI
    P5 --> D6
    D2 --> P6
    D8 --> P6
    P6 <-->|"튜터 답변"| OAI
    P6 --> D5
    P7 --> D7
    P7 -->|"관리자 조회"| D1
    P8 -->|"사용자 소유 데이터 삭제"| D2
    P8 --> D3
    P8 --> D4
    P8 --> D5
    P8 --> D6
    P8 --> D1
```

설명:
- **모든 프로세스(P2~P8)는 P1 의 토큰 검증을 먼저 통과**해야 한다. 개인 데이터 API 는 동의가 된 UID 만 쓴다(`require_consented_uid`).
- **P2 의 초안은 저장하지 않는다.** 사용자가 확정(`/api/plan/confirm`)할 때 `goals` 와 `tasks` 를 한 번에 저장하고, 확정 때 서버가 일정을 다시 계산한다.
- **P5 인사이트**는 학습당 1건(`insights`, 문서 ID = goal_id)이고, 기록·회고가 부족하면 AI 를 호출하지 않는다.
- **P6 튜터**는 검토된 자료(`rag_documents.json`)만 근거로 쓰고 출처가 없으면 근거 있는 것처럼 표시하지 않는다.
- **P7 피드백**은 user_id 를 저장하지 않는다(P8 삭제 대상이 아님). 관리자 판별은 환경변수 `ADMIN_UIDS`.
- **P8 삭제**는 `goals, tasks, study_logs, reflections, conversations, consent_records, insights, users` 의 사용자 소유 문서를 지운다. 피드백은 user_id 가 없어 남는다.

### 3-3. 레벨 1 상세: 외부 입출력을 터미널(화면명, API명)로 분리

3-2 는 프로세스와 저장소 중심의 개요이고, 여기서는 **외부 입출력을 터미널로 쪼갠다.** 터미널은 세 종류다.
- **[화면]** 학습자 또는 관리자가 보는 화면(화면 이름). 데이터는 화면에서 들어오고 화면으로 나간다.
- **[AI]** OpenAI 호출. 용도별로 분리한다(직무 예시, 과정·수준 추천, 계획 초안, 인사이트, 튜터 답변). 외부 서비스는 OpenAI 하나지만 프롬프트와 출력 스키마가 달라 별도 터미널로 그린다.
- **[인증]** Firebase Authentication(토큰 검증).

화살표 글자는 **API 이름**(메서드와 경로)이다. API 이름은 서버 코드에서, 화면별 호출은 프론트 코드에서 추출했다. 저장소는 원통, 프로세스는 둥근 사각형이다. 모든 API 는 P1 의 토큰 검증(`[인증]`)을 먼저 거친다(아래 그림에서는 생략).

#### 3-3-1. 화면과 API 대응표
| 터미널 [화면] | 사용하는 API | 프로세스 | AI 터미널 | 저장소 |
|---|---|---|---|---|
| 동의 창 | POST /api/consent | P1 | - | users, consent_records |
| 대시보드 | GET /api/dashboard/summary, PATCH /api/tasks/{id}, GET /api/user/profile | P4, P3 | - | goals, tasks, study_logs, insights, users |
| 학습 경로 설정 | POST /api/path/ideas, POST /api/path/recommend, POST /api/plan/generate, POST /api/plan/confirm, GET /api/tasks | P2 | 직무 예시, 과정·수준 추천, 계획 초안 | goals, tasks(확정 때만) |
| 학습 과제 계획 | GET /api/goals/{id}, GET /api/tasks, PATCH /api/tasks/{id}, GET /api/goals/{id}/references | P3, P6 | - | goals, tasks, 학습 자료(읽기) |
| 학습 실행 기록 | GET·POST·PATCH·DELETE /api/study-logs, POST /api/timer/start·finish·cancel, GET /api/timer/active, GET /api/goals, GET·PATCH /api/user/profile, GET·POST /api/goals/{id}/insight | P3, P5 | 인사이트 | tasks, study_logs, reflections, users, insights |
| 종합 학습 분석 | GET /api/analytics/overview | P4 | - | goals, tasks, study_logs |
| AI 튜터 | GET·POST /api/conversations, GET /api/conversations/{id}, POST /api/conversations/{id}/messages, GET /api/data/summary | P6 | 튜터 답변 | conversations, goals, 학습 자료(읽기) |
| 내 정보·설정 | GET /api/user/profile, POST /api/feedback, POST /api/user/delete-data | P1, P7, P8 | - | users, feedback, 사용자 소유 전체(삭제) |
| 관리자: 사용자 관리 | GET /api/admin/users | P7 | - | users |
| 관리자: 사용자 피드백 | GET /api/admin/feedback, GET /api/admin/feedback/summary, PATCH /api/admin/feedback/{id} | P7 | - | feedback |
- 화면 어디서나: GET /health(서버 깨우기 확인, 앱 첫 진입 때 ServerGate 가 호출).
- `GET /api/resources` 는 서버에 있으나 현재 화면에서 호출하지 않는다(자료 보관함 화면은 준비 중).

#### 3-3-2. P1 인증·동의 / P8 데이터 삭제 (동의 창, 내 정보·설정)
```mermaid
flowchart LR
    S1["[화면] 동의 창"]
    S2["[화면] 내 정보·설정"]
    F1["[인증] Firebase Auth"]
    P1("P1 인증·동의")
    P8("P8 데이터 삭제")
    D1[("users<br/>consent_records")]
    DX[("사용자 소유 데이터<br/>goals tasks study_logs<br/>reflections conversations insights")]

    S1 -->|"POST /api/consent<br/>약관 버전, 동의 항목"| P1
    P1 -->|"동의 결과"| S1
    S2 -->|"GET /api/user/profile"| P1
    P1 -->|"프로필, is_admin"| S2
    P1 <-->|"ID 토큰 검증, UID"| F1
    P1 --> D1
    S2 -->|"POST /api/user/delete-data"| P8
    P8 -->|"삭제 건수"| S2
    P8 --> DX
    P8 --> D1
```

#### 3-3-3. P2 학습 경로·계획 (학습 경로 설정)
```mermaid
flowchart LR
    S["[화면] 학습 경로 설정"]
    A1["[AI] 직무·목표 예시"]
    A2["[AI] 과정·수준 추천"]
    A3["[AI] 계획 초안"]
    P2a("P2a 직무 예시")
    P2b("P2b 과정·수준 추천")
    P2c("P2c 계획 초안 생성<br/>schedule.py 일정 계산")
    P2d("P2d 계획 확정<br/>일정 재계산, 겹침 검사")
    D2[("goals")]
    D3[("tasks")]

    S -->|"POST /api/path/ideas<br/>분야"| P2a
    P2a -->|"분야"| A1
    A1 -->|"직무 예시"| P2a
    P2a -->|"suggested_roles"| S
    S -->|"POST /api/path/recommend<br/>분야, 직무"| P2b
    P2b -->|"분야, 직무"| A2
    A2 -->|"과정, 수준표"| P2b
    P2b -->|"과정 목록, 수준"| S
    S -->|"POST /api/plan/generate<br/>과정, 수준, 기간, 주당 시간"| P2c
    P2c -->|"과정, 수준, 기간"| A3
    A3 -->|"과제 목록 초안"| P2c
    P2c -->|"초안과 주차 배치(저장 안 함)"| S
    S -->|"POST /api/plan/confirm<br/>client_request_id"| P2d
    P2d --> D2
    P2d --> D3
    P2d -->|"확정 결과"| S
    S -->|"GET /api/tasks"| D3
```

#### 3-3-4. P3 학습 실행·기록 (대시보드, 학습 과제 계획, 학습 실행 기록)
```mermaid
flowchart LR
    S1["[화면] 대시보드"]
    S2["[화면] 학습 과제 계획"]
    S3["[화면] 학습 실행 기록"]
    P3a("P3a 과제 상태·조회")
    P3b("P3b 타이머")
    P3c("P3c 학습 기록·회고")
    D1[("users<br/>active_timer, active_goal_id")]
    D3[("tasks")]
    D4[("study_logs<br/>reflections")]

    S1 -->|"PATCH /api/tasks/id<br/>완료 토글"| P3a
    S2 -->|"GET /api/tasks, PATCH /api/tasks/id"| P3a
    S3 -->|"GET /api/tasks"| P3a
    P3a --> D3
    P3a -->|"과제 목록, 누적 시간"| S3
    S3 -->|"POST /api/timer/start, finish, cancel<br/>GET /api/timer/active"| P3b
    P3b --> D1
    P3b -->|"기록 생성"| P3c
    S3 -->|"GET, POST, PATCH, DELETE /api/study-logs<br/>회고 포함"| P3c
    P3c --> D4
    P3c -->|"기록 목록"| S3
    S3 -->|"GET, PATCH /api/user/profile<br/>학습 전환"| D1
```

#### 3-3-5. P4 대시보드·분석 / P5 AI 인사이트
```mermaid
flowchart LR
    S1["[화면] 대시보드"]
    S2["[화면] 종합 학습 분석"]
    S3["[화면] 학습 실행 기록<br/>(인사이트 카드)"]
    A4["[AI] 인사이트"]
    P4("P4 요약·분석 계산")
    P5("P5 AI 인사이트<br/>insight_rules.py 충분/부족 판정")
    D2[("goals")]
    D3[("tasks")]
    D4[("study_logs<br/>reflections")]
    D6[("insights")]

    S1 -->|"GET /api/dashboard/summary"| P4
    S2 -->|"GET /api/analytics/overview"| P4
    P4 -->|"지표, 주간 활동, 학습 현황"| S1
    P4 -->|"분석 지표"| S2
    D2 --> P4
    D3 --> P4
    D4 --> P4
    D6 --> P4
    S3 -->|"GET /api/goals/id/insight<br/>POST /api/goals/id/insight"| P5
    D3 --> P5
    D4 --> P5
    P5 -->|"최근 기록과 회고 요약"| A4
    A4 -->|"진행 요약, 어려움, 다음 행동"| P5
    P5 --> D6
    P5 -->|"인사이트 또는 부족 안내"| S3
```

#### 3-3-6. P6 AI 튜터·참고자료 (AI 튜터, 학습 과제 계획)
```mermaid
flowchart LR
    S1["[화면] AI 튜터"]
    S2["[화면] 학습 과제 계획<br/>(참고자료)"]
    A5["[AI] 튜터 답변"]
    P6a("P6a 대화·질문 처리<br/>tutor.py 답변 검증")
    P6b("P6b 참고자료 찾기<br/>rag.py")
    D5[("conversations")]
    D2[("goals")]
    D8[("검토된 학습 자료<br/>읽기 전용")]

    S1 -->|"GET, POST /api/conversations<br/>GET /api/conversations/id<br/>GET /api/data/summary"| P6a
    S1 -->|"POST /api/conversations/id/messages<br/>질문"| P6a
    P6a -->|"질문, 근거 자료"| A5
    A5 -->|"답변"| P6a
    P6a -->|"답변, 출처, 키워드"| S1
    P6a --> D5
    D2 --> P6a
    D8 --> P6a
    S2 -->|"GET /api/goals/id/references"| P6b
    D2 --> P6b
    D8 --> P6b
    P6b -->|"자료와 출처"| S2
```

#### 3-3-7. P7 피드백·관리자 (내 정보·설정, 관리자 화면)
```mermaid
flowchart LR
    S1["[화면] 내 정보·설정<br/>(피드백 카드)"]
    S2["[화면] 관리자: 사용자 관리"]
    S3["[화면] 관리자: 사용자 피드백"]
    P7a("P7a 피드백 접수")
    P7b("P7b 관리자 조회·처리<br/>ADMIN_UIDS 확인")
    D1[("users")]
    D7[("feedback<br/>UID 저장 안 함")]

    S1 -->|"POST /api/feedback<br/>평점, 의견, client_request_id"| P7a
    P7a --> D7
    P7a -->|"접수 결과"| S1
    S2 -->|"GET /api/admin/users"| P7b
    D1 --> P7b
    P7b -->|"사용자 현황"| S2
    S3 -->|"GET /api/admin/feedback, summary<br/>PATCH /api/admin/feedback/id"| P7b
    D7 <--> P7b
    P7b -->|"피드백 목록, 집계"| S3
```

읽는 법: 한 화면이 여러 프로세스에 걸칠 수 있다(대시보드는 P4 요약과 P3 과제 토글). AI 터미널은 계획 생성 3개(직무 예시, 과정·수준 추천, 계획 초안), 인사이트 1개, 튜터 1개로 총 5개이고, 각각 OpenAI 호출 1종류에 해당한다. 사용자 입력과 AI 응답 원문은 로그에 남기지 않는다.

## 4. 인증 흐름 (익명 로그인 → 요청 → 소유권 확인)

```mermaid
sequenceDiagram
    participant B as 브라우저
    participant FE as 프론트(Vercel)
    participant FA as Firebase Auth
    participant BE as 백엔드(Render)
    participant FS as Firestore

    B->>FE: 사이트 열기
    FE->>BE: GET /health (서버 깨우기 확인)
    BE-->>FE: 모드, 상태
    FE->>B: 약관 동의 창
    B->>FE: 동의
    FE->>FA: 익명 로그인
    FA-->>FE: UID, ID 토큰
    FE->>BE: POST /api/consent + 토큰
    BE->>FA: 토큰 검증
    FA-->>BE: UID
    BE->>FS: users, consent_records 저장
    Note over B,FE: 브라우저가 로그인 상태를 저장(IndexedDB)
    B->>FE: 다음 방문(같은 브라우저·주소)
    FE->>FA: 저장된 로그인 복원
    FA-->>FE: 같은 UID, 새 ID 토큰
    FE->>BE: API 요청 + 토큰
    BE->>FA: 토큰 검증, UID 확인
    BE->>FS: 해당 UID 문서만 읽기·쓰기
    BE-->>FE: 응답
```

## 5. 학습 계획 생성과 확정 흐름

```mermaid
sequenceDiagram
    participant U as 학습자
    participant FE as 프론트
    participant BE as 백엔드
    participant AI as OpenAI
    participant FS as Firestore

    U->>FE: 분야 입력
    FE->>BE: POST /api/path/ideas
    BE->>AI: 직무·목표 예시 요청
    AI-->>BE: 예시
    BE-->>FE: 예시(저장 안 함)
    U->>FE: 과정, 현재·목표 수준, 기간, 주당 시간 선택
    FE->>BE: POST /api/path/recommend
    BE->>AI: 과정·수준 추천
    AI-->>BE: 결과(스키마 검증)
    FE->>BE: POST /api/plan/generate
    BE->>AI: 전체 과정 계획 초안 요청
    AI-->>BE: 초안
    BE->>BE: 스키마와 규칙 검증(위반 시 거부·재시도)
    BE-->>FE: 초안 + 일정 계산(저장 안 함)
    U->>FE: 확정
    FE->>BE: POST /api/plan/confirm(client_request_id)
    BE->>BE: 일정 서버 재계산, 겹침 검사(동시 2개까지)
    BE->>FS: goals, tasks 한 번에 저장(멱등)
    BE-->>FE: 확정 결과
```

## 6. 저장소 정리

| 구분 | 위치 | 내용 | 사용자 소유 | 삭제 요청 때 |
|---|---|---|---|---|
| 사용자 | Firestore `users` | 동의 버전, 활성 학습, 활성 타이머, 마지막 활동, 피드백 횟수 | 예 | 삭제 |
| 동의 | `consent_records` | 약관 버전, 동의 항목 | 예 | 삭제 |
| 학습 | `goals`, `tasks` | 목표, 과제, 일정 | 예 | 삭제 |
| 기록 | `study_logs`, `reflections` | 학습 기록, 회고 | 예 | 삭제 |
| 대화 | `conversations` | 튜터 대화, 출처, 키워드 | 예 | 삭제 |
| 인사이트 | `insights` | 학습당 1건 | 예 | 삭제 |
| 피드백 | `feedback` | 평점, 의견(UID 없음) | 아니오 | **남음** |
| 학습 자료 | `backend/data/rag_documents.json`, `resources_catalog.py` | 검토된 자료 | 공용 읽기 전용 | 해당 없음 |
| 로그인 상태 | 브라우저 IndexedDB(Firebase) | 익명 UID 와 토큰 | 브라우저 | 삭제 요청 시 브라우저 저장 UID 지움 |

## 7. 보안 경계 한눈에
| 경계 | 규칙 |
|---|---|
| 브라우저 ↔ 백엔드 | HTTPS, CORS 는 배포된 프론트 주소만, ID 토큰 필수 |
| 백엔드 ↔ Firebase | 토큰 검증, 서비스 계정(서버 환경변수) |
| 백엔드 ↔ OpenAI | 키는 서버에만, 입력·응답 원문은 로그에 남기지 않음 |
| 소유권 | UID 는 토큰에서만, 타인 문서 접근 403 |
| 배포 환경 | Render 에서는 dev 인증, memory 저장, 안전하지 않은 CORS 를 거부 |
| 관리자 | `ADMIN_UIDS` 에 든 UID 만 `/api/admin/*` |

## 8. 변경 시 갱신
라우트, 컬렉션, 외부 서비스가 바뀌면 이 문서와 `docs/erd_current.md` 를 같이 갱신한다. 계정 승격(`docs/auth_upgrade_design.md`)이 구현되면 §4 와 §6 의 로그인 항목을 바꾼다.
