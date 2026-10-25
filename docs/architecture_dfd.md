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

범례: **타원 = 터미널(외부 개체, 레벨 1 에서는 화면)**, 둥근 사각형 = 프로세스, 원통 = 데이터 저장소.

### 3-1. 레벨 0 (컨텍스트)

```mermaid
flowchart LR
    L(["학습자"])
    AD(["관리자<br/>(ADMIN_UIDS)"])
    FB(["Firebase<br/>Authentication"])
    OAI(["OpenAI"])
    SYS("PaceMate<br/>시스템")
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

### 3-2. 레벨 1: API 함수마다 프로세스, 터미널은 화면만

작성 규칙(사용자 지정, 2026-10-25):
1. **터미널(타원)끼리는 데이터 흐름이 없다.** 그래서 학습자, 관리자, OpenAI 터미널은 레벨 1 에서 쓰지 않는다.
2. **터미널(타원)은 화면만** 둔다(`[화면] 이름`). 학습자와 관리자는 화면을 통해서만 시스템과 만난다.
3. **API 함수 하나가 프로세스 하나**다(`P그룹.번호 메서드 경로`). 번호는 표 3-2-1 과 같다. 복잡해지면 나중에 레벨을 나눈다.
4. 저장소(원통)는 **프로세스와만** 연결한다(화면이나 저장소끼리 직접 잇지 않는다).
5. **OpenAI 호출은 터미널이 아니라 내부 프로세스**(`AI 호출: 용도`)로 그린다. 해당 API 프로세스가 입력을 넘기고 결과를 받는다. 모든 API 프로세스는 먼저 토큰 검증(Firebase)을 거치지만, 그림이 복잡해져서 생략한다(§4 인증 흐름 참고).

레벨 0(3-1)의 학습자, 관리자는 레벨 1 에서 **그들이 쓰는 화면 터미널들**로 풀린다(학습자 = 대시보드 등 7개 화면과 동의 창, 관리자 = 관리자 화면 2개). OpenAI 와 Firebase 는 레벨 1 에서 내부 호출로 흡수했다. 레벨 0 과의 균형을 엄격히 맞추려면 레벨 1 에 두 외부 시스템 터미널을 되살려야 한다(결정 필요, 아래 "열린 결정").

#### 3-2-1. 프로세스 목록 (API 40여 개 중 화면이 호출하는 것 + 서버에만 있는 것)
| 번호 | API | 호출하는 화면 터미널 | AI 호출 | 읽고 쓰는 저장소 |
|---|---|---|---|---|
| P1.1 | POST /api/consent | 동의 창 | - | users, consent_records (쓰기) |
| P1.2 | GET /api/user/profile | 내 정보·설정, 앱 공통(관리자 메뉴 표시), 학습 실행 기록(학습 전환) | - | users (읽기) |
| P1.3 | PATCH /api/user/profile | 학습 실행 기록(학습 전환) | - | users (쓰기) |
| P1.4 | POST /api/user/delete-data | 내 정보·설정 | - | users, consent_records, goals, tasks, study_logs, reflections, conversations, insights (삭제) |
| P1.5 | GET /health | 서버 깨우기 화면 | - | 없음 |
| P2.1 | POST /api/path/ideas | 학습 경로 설정 | 직무 예시 | 없음(저장 안 함) |
| P2.2 | POST /api/path/recommend | 학습 경로 설정 | 과정·수준 추천 | 없음 |
| P2.3 | POST /api/plan/generate | 학습 경로 설정 | 계획 초안 | goals (겹침 검사 읽기) |
| P2.4 | POST /api/plan/confirm | 학습 경로 설정 | - | goals, tasks (쓰기) |
| P3.1 | GET /api/goals | 학습 실행 기록(학습 전환) | - | goals |
| P3.2 | GET /api/goals/{id} | 학습 과제 계획 | - | goals |
| P3.3 | GET /api/goals/{id}/references | 학습 과제 계획 | - | goals, 학습 자료(읽기) |
| P3.4 | GET /api/tasks | 학습 과제 계획, 학습 실행 기록, 학습 경로 설정 | - | tasks, study_logs(누적) |
| P3.5 | PATCH /api/tasks/{id} | 대시보드, 학습 과제 계획 | - | tasks (쓰기) |
| P4.1 | GET /api/study-logs | 학습 실행 기록 | - | study_logs, reflections |
| P4.2 | POST /api/study-logs | 학습 실행 기록 | - | study_logs, reflections |
| P4.3 | PATCH /api/study-logs/{id} | 학습 실행 기록 | - | study_logs, reflections |
| P4.4 | DELETE /api/study-logs/{id} | 학습 실행 기록 | - | study_logs, reflections |
| P4.5 | POST /api/timer/start | 학습 실행 기록 | - | users (active_timer) |
| P4.6 | POST /api/timer/finish | 학습 실행 기록 | - | users, study_logs |
| P4.7 | POST /api/timer/cancel | 학습 실행 기록 | - | users |
| P4.8 | GET /api/timer/active | 학습 실행 기록 | - | users |
| P5.1 | GET /api/dashboard/summary | 대시보드 | - | goals, tasks, study_logs, insights |
| P5.2 | GET /api/analytics/overview | 종합 학습 분석 | - | goals, tasks, study_logs |
| P5.3 | GET /api/goals/{id}/insight | 학습 실행 기록(인사이트 카드) | - | insights |
| P5.4 | POST /api/goals/{id}/insight | 학습 실행 기록(인사이트 카드) | 인사이트 | tasks, study_logs, reflections (읽기), insights (쓰기) |
| P6.1 | GET /api/conversations | AI 튜터 | - | conversations |
| P6.2 | POST /api/conversations | AI 튜터 | - | conversations |
| P6.3 | GET /api/conversations/{id} | AI 튜터 | - | conversations |
| P6.4 | POST /api/conversations/{id}/messages | AI 튜터 | 튜터 답변 | conversations, goals, 학습 자료(읽기) |
| P6.5 | GET /api/data/summary | AI 튜터 | - | goals, tasks, study_logs |
| P7.1 | POST /api/feedback | 내 정보·설정 | - | feedback, users(횟수) |
| P7.2 | GET /api/admin/users | 관리자: 사용자 관리 | - | users |
| P7.3 | GET /api/admin/feedback | 관리자: 사용자 피드백 | - | feedback |
| P7.4 | GET /api/admin/feedback/summary | 관리자: 사용자 피드백 | - | feedback |
| P7.5 | PATCH /api/admin/feedback/{id} | 관리자: 사용자 피드백 | - | feedback (쓰기) |

**서버에는 있으나 현재 화면이 호출하지 않는 API**(프로세스로 정의하되 입력 터미널이 없어 그림에서는 제외): POST /api/goals, PATCH /api/goals/{id}, DELETE /api/goals/{id}, POST /api/tasks, DELETE /api/tasks/{id}, GET /api/resources(자료 보관함 화면 준비 중). 목표와 과제 생성은 화면에서는 P2.4(plan/confirm)가 맡는다.
저장소별 읽기·쓰기 표는 호출 코드를 함수 단위로 전수 확인한 것이 아니라 API 이름과 ERD 로 정리한 것이다.

#### 3-2-2. P1 인증·계정
```mermaid
flowchart LR
    S1(["[화면] 동의 창"])
    S2(["[화면] 내 정보·설정"])
    S3(["[화면] 앱 공통(관리자 메뉴)"])
    S4(["[화면] 학습 실행 기록(학습 전환)"])
    S5(["[화면] 서버 깨우기 화면"])
    P11("P1.1 POST /api/consent")
    P12("P1.2 GET /api/user/profile")
    P13("P1.3 PATCH /api/user/profile")
    P14("P1.4 POST /api/user/delete-data")
    P15("P1.5 GET /health")
    DU[("users")]
    DC[("consent_records")]
    DO[("사용자 소유 데이터<br/>goals tasks study_logs<br/>reflections conversations insights")]

    S1 -->|"약관 버전, 동의 항목"| P11
    P11 -->|"동의 결과"| S1
    P11 --> DU
    P11 --> DC
    S2 -->|"프로필 조회 요청"| P12
    S3 -->|"프로필 조회 요청"| P12
    S4 -->|"프로필 조회 요청"| P12
    DU --> P12
    P12 -->|"프로필, is_admin, 활성 학습"| S2
    P12 -->|"is_admin"| S3
    P12 -->|"활성 학습"| S4
    S4 -->|"active_goal_id"| P13
    P13 --> DU
    P13 -->|"수정된 프로필"| S4
    S2 -->|"삭제 요청"| P14
    P14 --> DU
    P14 --> DC
    P14 --> DO
    P14 -->|"삭제 결과"| S2
    S5 -->|"상태 확인 요청"| P15
    P15 -->|"상태, 실행 모드"| S5
```

#### 3-2-3. P2 학습 경로·계획 (AI 호출 내부 프로세스 포함)
```mermaid
flowchart LR
    S(["[화면] 학습 경로 설정"])
    P21("P2.1 POST /api/path/ideas")
    P22("P2.2 POST /api/path/recommend")
    P23("P2.3 POST /api/plan/generate")
    P24("P2.4 POST /api/plan/confirm")
    A1("AI 호출: 직무 예시")
    A2("AI 호출: 과정·수준 추천")
    A3("AI 호출: 계획 초안")
    SH("일정 계산<br/>schedule.py")
    DG[("goals")]
    DT[("tasks")]

    S -->|"학습 분야"| P21
    P21 -->|"분야"| A1
    A1 -->|"직무 예시"| P21
    P21 -->|"직무 예시"| S
    S -->|"분야, 직무"| P22
    P22 -->|"분야, 직무"| A2
    A2 -->|"과정, 수준표"| P22
    P22 -->|"과정 목록, 수준"| S
    S -->|"과정, 현재·목표 수준, 기간, 주당 시간"| P23
    DG -->|"진행 중 학습(겹침 검사)"| P23
    P23 -->|"과정, 수준, 기간"| A3
    A3 -->|"과제 초안"| P23
    P23 -->|"과제, 시간"| SH
    SH -->|"주차 배치"| P23
    P23 -->|"계획 초안(저장 안 함)"| S
    S -->|"확정 요청, client_request_id"| P24
    P24 -->|"과제, 시간"| SH
    SH -->|"주차 배치"| P24
    P24 --> DG
    P24 --> DT
    P24 -->|"확정 결과"| S
```

#### 3-2-4. P3 목표·과제 조회와 과제 상태
```mermaid
flowchart LR
    S1(["[화면] 대시보드"])
    S2(["[화면] 학습 과제 계획"])
    S3(["[화면] 학습 실행 기록"])
    S4(["[화면] 학습 경로 설정"])
    P31("P3.1 GET /api/goals")
    P32("P3.2 GET /api/goals/{id}")
    P33("P3.3 GET /api/goals/{id}/references")
    P34("P3.4 GET /api/tasks")
    P35("P3.5 PATCH /api/tasks/{id}")
    DG[("goals")]
    DT[("tasks")]
    DL[("study_logs")]
    DD[("학습 자료<br/>읽기 전용")]

    S3 -->|"목록 요청"| P31
    DG --> P31
    P31 -->|"학습 목록"| S3
    S2 -->|"학습 id"| P32
    DG --> P32
    P32 -->|"학습 상세"| S2
    S2 -->|"학습 id"| P33
    DG --> P33
    DD --> P33
    P33 -->|"참고자료, 출처"| S2
    S2 -->|"학습 id"| P34
    S3 -->|"학습 id"| P34
    S4 -->|"학습 id(확정 직후)"| P34
    DT --> P34
    DL --> P34
    P34 -->|"과제 목록, 기록 수, 누적 시간"| S2
    P34 -->|"과제 목록"| S3
    P34 -->|"과제 목록"| S4
    S1 -->|"완료 여부"| P35
    S2 -->|"완료 여부, 추천 요일"| P35
    P35 --> DT
    P35 -->|"수정된 과제"| S1
    P35 -->|"수정된 과제"| S2
```

#### 3-2-5. P4 학습 실행 기록·타이머
```mermaid
flowchart LR
    S(["[화면] 학습 실행 기록"])
    P41("P4.1 GET /api/study-logs")
    P42("P4.2 POST /api/study-logs")
    P43("P4.3 PATCH /api/study-logs/{id}")
    P44("P4.4 DELETE /api/study-logs/{id}")
    P45("P4.5 POST /api/timer/start")
    P46("P4.6 POST /api/timer/finish")
    P47("P4.7 POST /api/timer/cancel")
    P48("P4.8 GET /api/timer/active")
    DL[("study_logs<br/>reflections")]
    DU[("users<br/>active_timer")]

    S -->|"기간, 학습 id"| P41
    DL --> P41
    P41 -->|"기록 목록"| S
    S -->|"과제, 날짜, 분, 활동, 회고"| P42
    P42 --> DL
    P42 -->|"저장된 기록"| S
    S -->|"수정 내용, 회고 삭제"| P43
    P43 --> DL
    P43 -->|"수정된 기록"| S
    S -->|"삭제 요청"| P44
    P44 --> DL
    P44 -->|"삭제 결과"| S
    S -->|"과제 id"| P45
    P45 --> DU
    P45 -->|"타이머 시작 상태"| S
    S -->|"종료, 분(선택), 회고"| P46
    DU --> P46
    P46 --> DL
    P46 --> DU
    P46 -->|"저장된 기록"| S
    S -->|"취소 요청"| P47
    P47 --> DU
    P47 -->|"취소 결과"| S
    S -->|"조회 요청"| P48
    DU --> P48
    P48 -->|"진행 중 타이머"| S
```

#### 3-2-6. P5 대시보드·분석·인사이트
```mermaid
flowchart LR
    S1(["[화면] 대시보드"])
    S2(["[화면] 종합 학습 분석"])
    S3(["[화면] 학습 실행 기록<br/>(인사이트 카드)"])
    P51("P5.1 GET /api/dashboard/summary")
    P52("P5.2 GET /api/analytics/overview")
    P53("P5.3 GET /api/goals/{id}/insight")
    P54("P5.4 POST /api/goals/{id}/insight")
    AI("AI 호출: 인사이트")
    RU("충분/부족 판정<br/>insight_rules.py")
    DG[("goals")]
    DT[("tasks")]
    DL[("study_logs<br/>reflections")]
    DI[("insights")]

    S1 -->|"요약 요청"| P51
    DG --> P51
    DT --> P51
    DL --> P51
    DI --> P51
    P51 -->|"지표, 주간 활동, 학습 현황"| S1
    S2 -->|"분석 요청"| P52
    DG --> P52
    DT --> P52
    DL --> P52
    P52 -->|"분석 지표"| S2
    S3 -->|"조회 요청"| P53
    DI --> P53
    P53 -->|"저장된 인사이트"| S3
    S3 -->|"생성 요청, client_request_id"| P54
    DT --> P54
    DL --> P54
    P54 -->|"기록 수, 회고 수"| RU
    RU -->|"충분 또는 부족"| P54
    P54 -->|"최근 14일 기록·회고 요약"| AI
    AI -->|"진행 요약, 어려움, 다음 행동"| P54
    P54 --> DI
    P54 -->|"인사이트 또는 부족 안내"| S3
```

#### 3-2-7. P6 AI 튜터
```mermaid
flowchart LR
    S(["[화면] AI 튜터"])
    P61("P6.1 GET /api/conversations")
    P62("P6.2 POST /api/conversations")
    P63("P6.3 GET /api/conversations/{id}")
    P64("P6.4 POST /api/conversations/{id}/messages")
    P65("P6.5 GET /api/data/summary")
    AI("AI 호출: 튜터 답변")
    RG("자료 검색·답변 검증<br/>rag.py, tutor.py")
    DC[("conversations")]
    DG[("goals")]
    DT[("tasks")]
    DL[("study_logs")]
    DD[("학습 자료<br/>읽기 전용")]

    S -->|"목록 요청"| P61
    DC --> P61
    P61 -->|"대화 목록"| S
    S -->|"새 대화, client_request_id"| P62
    P62 --> DC
    P62 -->|"새 대화"| S
    S -->|"대화 id"| P63
    DC --> P63
    P63 -->|"대화 내용, 출처"| S
    S -->|"질문, client_request_id"| P64
    DG --> P64
    DC --> P64
    P64 -->|"질문, 학습 정보"| RG
    DD --> RG
    RG -->|"근거 자료"| P64
    P64 -->|"질문, 근거 자료"| AI
    AI -->|"답변"| P64
    P64 -->|"답변 검증, 출처, 키워드"| RG
    P64 --> DC
    P64 -->|"답변, 출처, 키워드"| S
    S -->|"요약 요청"| P65
    DG --> P65
    DT --> P65
    DL --> P65
    P65 -->|"학습 데이터 요약"| S
```

#### 3-2-8. P7 피드백·관리자
```mermaid
flowchart LR
    S1(["[화면] 내 정보·설정<br/>(피드백 카드)"])
    S2(["[화면] 관리자: 사용자 관리"])
    S3(["[화면] 관리자: 사용자 피드백"])
    P71("P7.1 POST /api/feedback")
    P72("P7.2 GET /api/admin/users")
    P73("P7.3 GET /api/admin/feedback")
    P74("P7.4 GET /api/admin/feedback/summary")
    P75("P7.5 PATCH /api/admin/feedback/{id}")
    DF[("feedback<br/>UID 저장 안 함")]
    DU[("users")]

    S1 -->|"평점, 의견, client_request_id"| P71
    P71 --> DF
    P71 --> DU
    P71 -->|"접수 결과"| S1
    S2 -->|"상태 필터, 쪽"| P72
    DU --> P72
    P72 -->|"사용자 현황"| S2
    S3 -->|"상태 필터"| P73
    DF --> P73
    P73 -->|"피드백 목록"| S3
    S3 -->|"집계 요청"| P74
    DF --> P74
    P74 -->|"집계"| S3
    S3 -->|"처리 상태"| P75
    P75 --> DF
    P75 -->|"수정된 피드백"| S3
```
(관리자 API 는 P7.2~P7.5 모두 `ADMIN_UIDS` 확인을 먼저 한다. 허용 목록 밖은 403.)

읽는 법:
- **모든 프로세스(P2~P7)는 P1 의 토큰 검증을 먼저 통과**한다. 개인 데이터 API 는 동의한 UID 만 쓴다.
- **P2.3 의 초안은 저장하지 않는다.** 사용자가 확정(P2.4)할 때 `goals` 와 `tasks` 를 한 번에 저장하고 서버가 일정을 다시 계산한다.
- **P6.4 튜터**는 검토된 자료만 근거로 쓰고, 출처가 없으면 근거 있는 것처럼 표시하지 않는다.
- **피드백(`feedback`)** 은 user_id 를 저장하지 않아 삭제 요청(P1.4) 때 남는다.
- 화면 하나가 여러 프로세스를 부른다(예: 학습 실행 기록 화면은 P1.2, P1.3, P3.1, P3.4, P4.1~P4.8, P5.3, P5.4 를 부른다).

열린 결정(사용자):
1. 레벨 0 과의 균형: 지금은 레벨 1 에서 OpenAI, Firebase 를 내부 프로세스로 흡수했다. 엄격히 맞추려면 두 외부 시스템 터미널(OpenAI, Firebase)을 되살리거나, 레벨 0 도 화면 터미널로 바꿔야 한다.
2. 프로세스를 그룹(P1~P7)으로 묶는 레벨 1 개요를 따로 둘지(지금은 API 단위 레벨 1 만 있다). 보통은 상위 레벨 1 은 7개 그룹, 하위 레벨 2 가 API 단위다.

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
