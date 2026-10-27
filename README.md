# PaceMate (페이스메이트) — AI 학습 플래너

독학 학습자가 배우고 싶은 분야와 목표를 자유롭게 입력하면, AI 가 과정과 수준을 제안하고 현재 수준에서 목표 수준까지의 전체 학습 계획을 만들어 주는 웹 서비스입니다. 학습 기록과 회고를 남기면, AI 튜터와 인사이트가 내 기록과 검토된 참고자료를 바탕으로 다음 행동을 돕습니다.

- **서비스 주소:** (배포 주소 추가 예정)
- **대상:** 부트캠프 수강생, IT 취업 준비생 등 장기 학습 목표를 가진 독학 학습자
- **기간:** 14일 MVP + 사용자 테스트·개선 (코디세이 AI Native 최종 프로젝트)

## 1. 해결하려는 문제
| 문제 | PaceMate 의 해결 |
|---|---|
| 큰 학습 목표를 실제 가용 시간에 맞는 작은 과제로 나누기 어렵다 | AI 가 과정·수준을 제안하고, 전체 과제 목록을 만든 뒤 서버가 주당 가능 시간에 맞춰 주차에 배치 |
| 일반 AI 답변은 내 계획과 지난 회고를 모른다 | 튜터가 내 학습 요약과 최근 회고(장기 메모리), 검토된 자료(RAG)를 함께 참고 |
| 계획과 실행 기록이 끊겨 진도를 알기 어렵다 | 과제별 타이머·기록·회고, 대시보드의 오늘 추천 과제와 진행률, AI 인사이트 |

## 2. 주요 기능
1. **동의 후 익명 시작:** 동의 전에는 계정과 개인 데이터를 만들지 않습니다. 이메일을 받지 않습니다.
2. **AI 학습 경로와 계획:** 자유 입력 분야 → AI 의 직무 예시·과정·수준 제안 → 현재·목표 수준 선택 → 전체 계획 초안 → 편집 후 확정(확정할 때만 저장).
3. **학습 실행 기록:** 과제별 시작·종료 타이머, 직접 입력, 기록 수정·삭제, 한 줄 회고와 태그.
4. **AI 튜터:** 검토된 자료와 내 학습 요약·회고를 참고해 답하고, 출처를 표시합니다. 대화는 저장되고 다시 불러올 수 있습니다.
5. **진행 현황과 AI 인사이트:** 대시보드(지표, 오늘 추천 과제, 주간 활동), 종합 학습 분석, 요청할 때 만드는 인사이트.
6. **복수 학습:** 진행 중인 학습을 최대 2개까지 두고 전환합니다.
7. **관리자:** 사용자 관리(마스킹된 현황), 사용자 피드백, 참고자료 수집·승인(AI 는 제안만, 사람이 승인).
8. **AI 생성 안내와 데이터 삭제:** 모든 AI 결과에 생성형 AI 안내를 표시하고, [내 정보·설정]에서 내 데이터를 직접 삭제할 수 있습니다.

## 3. AI 활용 방식
| 기법 | 어디에 | 어떻게 |
|---|---|---|
| **생성형 AI**(OpenAI, 기본 `gpt-4o-mini`) | 직무 예시, 과정·수준 제안, 전체 계획, 튜터 답변, 인사이트, 참고자료 분류 제안 | 모든 AI 호출은 백엔드에서만 합니다. 결과는 서버가 **스키마와 규칙으로 검증**하고, 어기면 조용히 고치지 않고 거부한 뒤 재시도합니다. 주차·요일·합계 같은 계산은 AI 에 맡기지 않고 서버가 정합니다 |
| **RAG**(필수 기술 1) | AI 튜터 | 팀이 검토한 학습 자료 10건(사람이 검토한 요약 조각 53개)을 서버에 두고, 질문과 관련된 조각을 키워드 기반으로 검색해 프롬프트에 넣습니다. 근거가 없으면 자료 기반 답변인 것처럼 표시하지 않습니다. 링크 전용 자료 31건은 계획 화면과 튜터의 참고 링크로만 씁니다 |
| **Long-term Memory**(필수 기술 2) | AI 튜터, 인사이트 | 사용자별 학습 기록과 회고를 저장하고, 질문마다 본인 UID 의 학습 요약과 최근 회고(최대 5건, 질문 키워드 일치 우선)를 맥락으로 넣습니다. 튜터 대화도 저장해 이어 갑니다 |
| 사람 승인 절차 | 참고자료 수집(관리자) | AI 는 후보 분류만 제안하고 승인은 사람이 합니다. 외부 주소는 허용 도메인·사설 주소 차단 등 검사(SSRF 방어)를 통과해야 하고, 페이지 본문은 AI 에 넣지 않습니다 |

AI 를 개선해 온 과정(현상 → 원인 → 결정 → 효과)은 `docs/ai_improvement_log.md` 에 있습니다.

## 4. 팀원 및 역할
영역은 모듈 경계(REST API 계약, DB 처리, AI 처리, 관리자 수집 모듈)로 나누고, **구현 담당과 검증 담당을 서로 다른 팀원**으로 교차 배정했습니다(상세: 서비스기획서 9장, 업무량 비교: `docs/team_workload.md`).

| 영역 | 범위 | 구현 | 검증 |
|---|---|---|---|
| ① 프론트엔드(사용자 UI) | 사용자 화면, 상태 관리, API 연결, 로딩·오류·서버 준비 안내 | member1 | member2 |
| ② 백엔드(DB 인터페이스) | 인증·권한(UID), Firestore, 학습 데이터 API, 배포, API/DTO 계약 관리 | member2 | member1 |
| ③ 백엔드(AI 인터페이스) | AI 호출·프롬프트·출력 검증, RAG 검색, 계획·튜터·인사이트 API, 튜터 대화 관리 | member3 | member4 |
| ④ 관리자 모듈 | 참고자료 수집·승인(수집용 AI 포함), 사용자 관리, 사용자 피드백 화면 | member4 | member3 |

구현에는 AI 코딩 도구를 사용했고, 담당 팀원이 결과에 책임집니다. 개발 세션과 검증(PM) 세션을 분리해 운영한 방식은 `docs/project_operating_playbook.md` 에 있습니다.

## 5. 기술 스택과 선정 근거
| 영역 | 선택 | 이유 |
|---|---|---|
| 프론트엔드 | Next.js, TypeScript (Vercel 배포) | 화면 상태가 많은 학습 흐름을 타입으로 안전하게 관리, 무료 배포와 HTTPS 를 바로 사용 |
| 백엔드 | Python FastAPI (Render 배포) | AI·데이터 처리를 Python 으로 작성, 요청·응답 DTO 검증과 OpenAPI 문서(`/docs`) 자동 생성 |
| 인증·DB | Firebase Authentication(익명), Firestore | 이메일 없이 익명 UID 로 시작, 서버 SDK 로 UID 별 데이터 격리 |
| AI | OpenAI API (모델은 환경변수로 지정) | 구조화된 JSON 출력을 서버에서 검증하기 쉬움 |
| RAG | 서버 배포물에 포함한 소규모 검토 자료 + 메모리 내 키워드 검색 | 14일 안에 근거를 사람이 검토할 수 있는 규모로 시작. 별도 벡터 DB 없이 동작하고, 근거가 없을 때를 분명히 구분 |
| 버전 관리 | GitHub | 소스·문서·진행 이력 |

선정 근거의 상세는 `PRD.md` 10장입니다.

## 6. 구조
- 요청 흐름: 프론트 → (Firebase ID 토큰) → FastAPI → Firestore / OpenAI. 프론트는 DB 와 AI 를 직접 부르지 않습니다. 서버는 **토큰에서만 UID 를 정하고** 요청 본문의 사용자 정보를 믿지 않습니다.
- 데이터 흐름도(DFD, 레벨 0~3): `docs/dfd_by_module.md`
- 데이터 구조(ERD): `docs/erd_current.md`
- API 명세: `docs/phase1_design.md`, 실행 중인 서버의 `/docs`

```
frontend/   Next.js 앱 (components/: 화면, lib/: API·날짜·상태 도우미)
backend/    FastAPI 앱 (main.py: API, ai_client.py: AI 호출, rag.py: 검색, data/: 검토 자료)
firebase/   Firestore 보안 규칙과 인덱스
mockup/     표준 화면 목업 (index.html)
docs/       설계, 지시서, 보고서, 검증 기록
```

## 7. 실행 방법 (로컬)
필요: Node.js 20.9 이상(이 작업 환경은 24 LTS), Python 3.12(`.python-version`).

**백엔드**
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn main:app --reload --port 8001 --env-file .env
```
상태 확인 `http://localhost:8001/health`, API 문서 `http://localhost:8001/docs`.

**프론트엔드**
```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```
`http://localhost:3000` 을 엽니다. 프론트는 `NEXT_PUBLIC_API_BASE_URL` 로 백엔드를 찾고, 백엔드의 `CORS_ORIGINS` 에 프론트 주소를 정확히 넣어야 합니다.

**인증 모드:** 예시 환경 파일은 **dev 모드**(백엔드 `AUTH_MODE=dev`, `STORE_BACKEND=memory`, 프론트 `NEXT_PUBLIC_AUTH_MODE=dev`)라 Firebase 키 없이 동의 → 익명 시작 흐름이 동작합니다. 데이터는 백엔드 메모리에 있어 재시작하면 사라집니다. 실제 Firebase 를 쓰려면 `AUTH_MODE=firebase`, `STORE_BACKEND=firestore`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `NEXT_PUBLIC_FIREBASE_*` 를 설정합니다(`docs/firebase_setup_guide.md`). AI 기능에는 `OPENAI_API_KEY` 가 필요합니다.

**테스트**
```powershell
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest            # 2026-10-27 기준 1,264건 통과

cd ../frontend
npm run typecheck
npm test                    # 2026-10-27 기준 183건 통과
npm run build
```

## 8. 배포
- 프론트는 Vercel, 백엔드는 Render, 인증·DB 는 Firebase(모든 값은 같은 Firebase 프로젝트). 절차와 환경변수: `docs/deploy_guide.md`, 배포 전 점검: `docs/pre_deploy_checklist.md`.
- 배포 환경(`RENDER` 변수 있음)에서는 dev 모드, 메모리 저장소, 안전하지 않은 `CORS_ORIGINS`(`*`, localhost, http, 끝의 `/`), 비어 있는 `FIREBASE_SERVICE_ACCOUNT_JSON`·`OPENAI_API_KEY` 이면 **서버가 시작을 거부**합니다. 메시지에는 규칙·변수 이름만 나오고 값은 나오지 않습니다. `API_DOCS_ENABLED=false` 로 `/docs` 를 끌 수 있습니다.
- 참고자료 관련 스위치는 모두 기본 꺼짐입니다: `RESOURCE_READ_SOURCE=file`(기본, 검토 파일만) / `file+approved`(관리자 승인 자료도 읽음), `COLLECTORS_ENABLED`(`direct_link`, `ai_topic`), `FIELD_STATS_ENABLED`. 허용 도메인은 `backend/data/allowed_domains.json`.

## 9. 결과
- **배포:** 프론트(Vercel)와 백엔드(Render)에 배포했고, Firebase 실연동(익명 인증, Firestore 저장, UID 격리)을 확인했습니다.
- **검증:** 개발 보고를 그대로 믿지 않고 검증(PM) 세션이 코드·테스트·실제 호출로 확인했습니다. Phase 별 검증 기록은 `docs/*_verification*.md`, MVP 이후 변경 기록은 `docs/change_management.md`.
- **사용자 테스트:** 진행 예정(테스터 5명 이상, 익명 설문 `docs/user_test_survey.md`). 결과, 설문 요약, 피드백 반영 내역은 테스트 후 이 절에 추가합니다.
- **한계와 이후 계획:** MVP 에서 제외한 Function Calling 튜터 Agent, 리마인더 자동화, 멀티모달 등은 서비스기획서 10장과 `docs/post_mvp_backlog.md` 에 있습니다.

## 10. 문서 안내
| 문서 | 내용 |
|---|---|
| `mission.md` | 과제 요구사항과 평가 기준 |
| `서비스기획서.md` | 무엇을 왜 만드는가(문제, 대상, 범위, 역할) |
| `PRD.md` | 기능 요구사항과 수용 기준(FR-01~08), 비기능, 기술 기준 |
| `TASK.md` | 14일 MVP 작업 계획과 이력(동결) |
| `docs/change_management.md` | MVP 이후 변경 기록(CR 번호) |
| `docs/ai_improvement_log.md` | AI 개선 이력 |
| `mockup/index.html` | 표준 화면 목업 |

## 11. 비밀값
실제 비밀값(OpenAI 키, Firebase 서비스 계정 등)은 커밋하지 않습니다. 로컬의 `backend/.env`, `frontend/.env.local`(Git 제외)이나 배포 플랫폼의 비밀 설정에만 둡니다. `.env.example` 에는 이름과 안전한 기본값만 있습니다. `reference-AI NATIVE M -2/` 는 비교용 임시 참고 폴더로 저장소에서 제외되며 PaceMate 의 일부가 아닙니다.
