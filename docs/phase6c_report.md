# Phase 6C 보고서 — 학습 자료 접근성 개선

작성: 개발팀, 2026-10-25. 기준: docs/phase6c_dev_prompt.md. Phase 7 은 시작하지 않았다.

## 요약
- A(링크 31건 추가), B(점수 기반 매칭), C(서버 생성 검색 링크), D(튜터 키워드와 함께 보면 좋은 자료) 구현 완료.
- 테스트: backend pytest **597 통과**(6C 직전 539 + 새 58: `test_phase6c.py` 58건, 기존 `test_resources_catalog.py` 기대값 3건 수정·1건 보강 포함), frontend `npm test` **72 통과**(66 + 새 6), `npm run typecheck`, `npm run build` 통과.
- 실제 OpenAI 호출 **2회**(자료 있는 질문 1, 자료 없는 질문 1; 빈 포트 8123, dev + memory, `.env` 미수정, 끝나고 서버 종료 확인). 브라우저(실제 Chrome, playwright)로 두 화면의 새 요소를 확인했다.

## 변경 요약
| 영역 | 내용 | 파일 |
|---|---|---|
| A 데이터 | `docs/phase6c_resource_links.md` 표 31건을 링크 전용 자료로 추가(`chunks: []`, `verified: true`, `verified_at: "2026-10-24"`, `license: "링크만 제공(원문 복제 없음)"`, `tags`, `link_only: true`). 기존 10건과 `rag_chunks.json` 은 그대로(JSON diff 는 추가만). URL·제목은 표를 파싱해 그대로 넣었고 표와 일치하는지 테스트로 확인 | `backend/data/rag_documents.json` |
| A 규칙 | 링크 전용 자료는 `rag.search` 인덱스와 튜터 출처(sources)에서 제외 | `backend/rag.py` |
| B 매칭 | 첫 토큰 일치 → 점수 기반(아래 "매칭 규칙") | `backend/resources_catalog.py` |
| C 검색 링크 | `search_links(field, course, extra_terms)` 순수 함수. 구글 검색, 구글 "공식 문서" 검색, 유튜브 검색 3개, 검색어 200자 제한, 퍼센트 인코딩(`quote(safe="")`). 라벨은 모두 "(검토 전 외부 링크)" | `resources_catalog.py` |
| C API | `GET /api/goals/{id}/references` 에 `search_links` 추가(항상 존재). `plan/generate` 응답은 변경 없음 | `main.py`, `schemas.py` |
| D 튜터 | `AITutorAnswer.search_keywords`; 서버 검증(최대 3개, 각 1~30자, `http`·`://`·`www.` 포함 시 거부 → 재시도), `relevant=false` 면 버림, 출처가 있으면 버림. 출처 없는 답변에는 본문에 "더 찾아볼 키워드: a, b, c" 줄을 "참고한 등록 자료가 없어요" 안내 앞에 붙임. 메시지에 `search_keywords` 저장 | `ai_schemas.py`, `tutor.py`, `main.py`, `prompts.py` |
| D 링크 | `search_links`(키워드 기반)와 `related_links`(출처 있는 답변에서 현재 학습과 매칭된 자료 최대 2건, 이미 출처인 자료 제외)는 **저장하지 않고 응답 때** 만든다. 대화 상세 조회와 멱등 재요청에서도 같은 방식 | `tutor.decorate`, `main.py` |
| 프론트 | 검색 링크·함께 보면 좋은 자료 순수 함수와 화면 | `lib/searchLinks.ts`, `lib/tutorState.ts`, `components/WeeklyPlanScreen.tsx`, `components/TutorScreen.tsx`, `app/globals.css` |
| 계약 문서 | `docs/erd_current.md`(conversations.messages), `docs/phase1_design.md`(메시지 구조, references·conversations API 행) 갱신. 프론트 타입은 위 파일에 포함 | |

## API / DTO 변경 표
| 대상 | 변경 | 호환성 |
|---|---|---|
| `GET /api/goals/{id}/references` | 응답에 `search_links: [{label, url}]` 추가(항상 존재, 최대 3개). `references` 는 최대 5건 | 필드 추가 |
| `MessageItem` (대화 상세, 메시지 전송 응답) | `search_keywords: string[]`(저장), `search_links: [{label,url}]`, `related_links: [{title,source_name,url}]`(응답 때 생성) 추가. 기본값은 빈 목록 | 필드 추가, 옛 저장 메시지도 로드됨(테스트) |
| `AITutorAnswer` (내부) | `search_keywords` 추가(서버 검증은 `tutor.validate_tutor_answer`) | 내부 |
| 새 스키마 | `SearchLinkItem`, `RelatedLinkItem` | |
| `plan/generate` | 응답 변경 없음. 단, 내부 `match_references` 가 바뀌어 `references` 의 내용은 새 규칙을 따른다 | |

## 매칭 규칙 (B)
입력 = 학습의 `field` + `course`. 토큰화는 기존 `_TOKEN_PATTERN`(영문·숫자, 한글) 소문자.
1. **후보 조건(정밀도):** 분야(field) 토큰이 자료의 tags 또는 category 에 하나 이상 일치해야 후보. 과정(course) 글자만으로는 후보가 되지 않는다(예: 과정 "기본문법" 이 JavaScript 자료에 붙는 오류 방지).
2. **점수:** (입력 토큰 중 tags 토큰과 일치하는 수) + (입력 토큰 중 category 토큰과 일치하는 수). 상위 최대 5건(동점은 id 순). 점수 0 이면 없음.
3. **불용어(점수에서 제외):** 개발, 개발자, 기초, 입문, 코딩, 학습, 공부, 과정, 기본, 초급, 강의, development, developer, basic, basics, beginner, coding, study, course, learn. ("개발자", "기본", "초급", "강의" 와 영문 일반어는 지시서 목록에 더해 개발팀이 추가했다.)
4. **일치 방식:** 영문은 완전 일치만(부분 문자열·접두 일치 없음 → Java ≠ JavaScript). **한글 접두 결정:** 한글 tag/category 토큰(2자 이상)이 입력 토큰의 접두이고 뒤에 붙은 글자가 2자 이하(조사)일 때만 허용("영어를"~"영어", "자바를"~"자바"). 뒤가 3자 이상이면 불허라 "자바스크립트" 는 "자바" 에 맞지 않는다(rag.py 의 양방향 접두 규칙보다 보수적).
5. **짧은 분야 가드:** 기존 "3글자 미만 분야는 매칭 없음"은 **영문(ASCII)에만** 남겼다("a", "AI" 는 여전히 매칭 없음). 한글 "영어", "웹" 같은 2글자 분야는 정확 일치 방식이라 허용했다(안 그러면 "영어" 학습에 영어 자료가 안 붙는다).

대표 결과(실제 데이터, 개발팀 확인):
| 입력(분야 / 과정) | 결과 id |
|---|---|
| Python 개발 / 기본문법 | doc_001, link_026, doc_002, doc_003, link_022 |
| 웹 프론트엔드 개발자 / React | link_006, link_008, link_001, link_002, link_003 |
| 영어 회화 | link_030, link_031 |
| 데이터 분석 입문 / pandas | link_022, link_023, link_024, doc_006, link_018 |
| Java | link_014, link_015 |
| VIBE CODING, 우주공학, UX 디자인/기초, 개발/입문 | 없음 |

### 바뀐 기대값 (기존 `test_resources_catalog.py`)
| 테스트 | 이전 기대 | 새 기대 | 이유 |
|---|---|---|---|
| `Python / 기초` | 결과 전부 category 에 python | category 또는 tags 에 python, `doc_006`(SQL) 은 없음 | tags 로 pandas·생활코딩이 붙음 |
| `Python 개발 / 기본문법` (두 테스트) | 정확히 3건 | 3~5건, doc_001·002·003 포함, doc_004·005·006 제외 | 링크 자료 추가와 최대 5건 |
| `Java` | 매칭 없음 | link_014, link_015 만(JavaScript 문서는 없음) | 이제 실제 Java 링크 자료가 있어 "없음"이 오히려 틀림. "Java ≠ JavaScript" 의도는 유지 |
- 변경 없이 통과: UX 디자인≠SQL 기초, 1글자·2글자 영문 분야, 우주공학, 일반어만 있는 입력.
- 5D 테스트(`GET references` 가 `match_references` 와 같은 결과)는 수정 없이 통과.
- **참고:** Python 분야에 pandas(link_022)·생활코딩이 함께 나온다. tags 에 `python` 이 있어서이며 학습자에게 유용할 수 있다고 판단해 그대로 두었다. 싫으면 PM 이 tags 를 조정한다.

## 화면 대조표 (mockup/index.html 의 page-wbs, page-tutor 와 비교)
| 요소 | 목업 | 구현 | 판정 |
|---|---|---|---|
| 주간 계획: "연결된 참고자료" 카드의 자료 항목 | 제목, "{출처} · {분류}", 원문 보기 | 같음(`sourceLine`) | 일치 |
| 주간 계획: "직접 검색해 보기" 소제목, 링크 3개, "검토 전 외부 링크예요." | 없음 | 구분선 아래 소제목, 링크 3개, 작은 글씨 | **구현에만 있음(의도적)** |
| 주간 계획: 자료 없음 안내 + 검색 링크 | 안내만 | 안내 아래에도 검색 링크 표시 | **구현에만 있음(의도적)** |
| 튜터 3열 레이아웃, "AI 생성 · 참고용", "참고한 자료가 없어요" 문구 | 있음 | 그대로 유지 | 일치 |
| 튜터: 출처 없는 답변 아래 "더 찾아볼 키워드: …" 줄 | 없음 | 본문에 포함(서버가 붙임) | **구현에만 있음(의도적)** |
| 튜터: 말풍선 하단 "직접 검색해 보기: 링크 3개" | 없음 | 출처 없는 답변에 표시 | **구현에만 있음(의도적)** |
| 튜터: 우측 패널 "함께 보면 좋은 자료"(출처 있는 답변) | 없음 | 제목, 출처 이름, 원문 보기 최대 2건 | **구현에만 있음(의도적)** |
| 튜터: 우측 패널 "직접 검색해 보기" + 경고 문구 | 없음 | 링크 3개 + "검토 전 외부 링크예요." | **구현에만 있음(의도적)** |
PM 이 목업을 맞춘다. 스크린샷(개발팀 임시 폴더, 저장소 밖): `c6c_wbs.png`, `c6c_tutor_sources.png`, `c6c_tutor_nosource.png`.

## 브라우저·실제 AI 확인 결과 (실제 Chrome, dev + memory, 실제 OpenAI 2회)
데이터: 학습 "Python 개발 / 기본문법". 응답 문장은 기록하지 않고 구조만 확인했다.
| 확인 | 결과 |
|---|---|
| 주간 계획 "연결된 참고자료": 검토 자료 5건 + "직접 검색해 보기" 소제목 + 링크 3개(새 탭, `noreferrer`, 라벨마다 "(검토 전 외부 링크)", 호스트는 구글·유튜브만) + 작은 글씨 | 통과 |
| 질문 1("리스트에 값을 추가하는 방법을 알려줘", 자료 있음): 출처 표시 있음, 패널에 "함께 보면 좋은 자료" 2건 | 통과 |
| 질문 2("공부 동기를 오래 유지하는 요령이 있을까요?", 자료 없음): "더 찾아볼 키워드: …" 줄이 "참고한 등록 자료가 없어요" 앞에 있음, 말풍선 아래 검색 링크 3개, 패널 "직접 검색해 보기" 3개, 기존 "참고한 자료가 없어요. 일반적인 학습 조언이에요." 유지 | 통과 |
| 튜터 화면의 모든 링크 | 서버 템플릿(구글·유튜브) 링크뿐 |
| 서버 로그에 질문·키워드·UID 문자열 | 없음(검사: 0건) |
- 모델 호출은 모델 클라이언트를 감싸 센 값 2회(재시도 없음).

## 보안·품질 확인
- AI 가 쓴 URL 이 응답에 들어갈 경로가 없다: 키워드에 URL 이 있으면 3회 재시도 후 502 와 저장 없음(테스트), 정상 키워드는 템플릿에만 들어가 퍼센트 인코딩됨. 검색 링크 외에 응답의 URL 은 `rag_documents.json` 값뿐.
- 인코딩: `&`, `#`, `"`, `%`, `?`, 공백, 한글이 든 학습 이름에서 매개변수가 하나만 유지되고 fragment 도 생기지 않음(테스트 6가지 문자열).
- 프론트는 서버가 준 URL 도 `https:` 가 아니면 렌더하지 않는다(`visibleSearchLinks`, `visibleRelatedLinks`).
- 로그에 질문·답변·키워드 원문 없음(`caplog` 테스트).

## 미검증
- Firebase 모드(실제 Firestore)에서의 `search_keywords` 저장과 옛 메시지 조회. 코드는 저장소 추상화를 통해서만 접근한다.
- 링크 URL 이 배포 시점에도 열리는지(배포 직전 `docs/pre_deploy_checklist.md` 에서 재확인). link_015(Spring)는 PM 표에서 "200만 확인"이라 제목 대조가 안 된 항목이며 그대로 넣었다.
- 모바일 폭 화면, 회고·출처가 매우 많은 경우의 레이아웃.
- 모델이 `search_keywords` 를 얼마나 자주 지키는지 표본: 실제 호출 2회뿐이라 통계적 의미 없음(둘 다 첫 시도에 통과).

## 열린 결정
1. 한글 별칭: "자바스크립트", "리액트" 같은 한글 입력은 tags 에 한글이 있는 자료에만 맞는다(예: "자바스크립트"는 기존 JavaScript 문서 category 가 영문이라 매칭 없음). 필요하면 PM 이 tags 에 별칭을 추가하거나, 개발팀이 별칭 사전을 만들지 정한다.
2. Python 분야에 pandas 등 데이터 자료가 함께 나오는 것을 허용할지(tags 조정으로 해결 가능).
3. 짧은 영문 분야("AI")를 계속 매칭 없음으로 둘지. 이제 `link_025`(머신러닝 단기집중과정)에 tag `ai` 가 있어 "AI" 학습자에게 맞을 수 있으나, 기존 회귀 테스트 의도(짧은 영문은 오매칭 위험)를 유지했다.
4. 불용어에 개발팀이 "개발자", "기본", "초급", "강의" 와 영문 일반어를 추가했다. 지시서 목록 밖이므로 PM 확인 요청.

## 커밋에 포함하지 않은 것
`frontend/AGENTS.md`, `frontend/next-env.d.ts`, `서비스기획서.md`(내가 바꾸지 않은 변경).
