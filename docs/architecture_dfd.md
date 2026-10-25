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

### 3-2. 레벨 1 (프로세스와 저장소)

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
