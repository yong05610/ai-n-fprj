# Phase 6C 수정 보고서 — 자유 입력 분야에서의 자료 매칭

작성: 개발팀, 2026-10-25. 기준: docs/phase6c_fix_instructions.md (대상 커밋 67d0a46). Phase 5F, 7 은 시작하지 않았다.

## 요약
- R1(과정 보완 매칭), R2(한글 별칭 tags), R3(짧은 영문 허용 목록) 모두 구현했다.
- backend pytest **623 통과**(수정 전 597 + 새 26: `test_phase6c_fix.py`. 기존 테스트 기대값 수정은 아래 "바뀐 기대값 목록" 참고). 프론트는 변경 없음(typecheck, test, build 를 다시 하지 않음 → 이번 변경 범위 밖).
- §1 표의 입력이 모두 기대대로 나온다(아래 전후 표). "요리 / 한식"과 "개발 / 입문"은 계속 빈 결과.
- 실제 OpenAI 호출은 하지 않았다(튜터 `related_links` 는 가짜 AI 로 테스트: 학습 "VIBE CODING / 웹 개발의 기초"에서 출처 있는 답변에 `related_links` 가 1~2건 나온다). 실제 서버 확인은 PM 몫.

## 변경 내용
| 항목 | 내용 | 파일 |
|---|---|---|
| R1 | 분야 토큰이 어떤 자료의 tags/category 에도 안 맞으면(후보 0) **과정 토큰만으로 다시 점수**를 계산한다(같은 점수 방식, 상위 5건). 이때 자료는 과정 토큰이 **tags 와 정확히 일치**해야 후보다(도메인 단어 조건). 분야가 맞으면 이전 동작 그대로 | `resources_catalog.py` |
| R1 보조 | 일반어 + 조사("개발의", "기초를", "과정에서" 등)도 일반어로 취급. 예전에는 "개발의" 가 일반어가 아니어서 "웹 개발의 기초"의 의미 있는 토큰이 흐려졌다. 조사 목록은 의, 를, 을, 은, 는, 이, 가, 에, 로, 와, 과, 도, 에서, 으로 로 한정해 "기본문법" 같은 과정명("기본"+"문법")은 일반어가 되지 않게 했다 | `resources_catalog.py` |
| R1 순위 | 동점일 때 **자료의 앞쪽 tag 에 맞은 것이 위**(tags 는 자료의 주요 주제 순서). Python 자료(`python` 이 첫 tag)가 pandas 등 데이터 자료보다 위에 온다 | `resources_catalog.py` |
| R2 | 기존 10건에 tags 추가(파이썬, 자바스크립트, js, 깃, 넥스트, 리액트, 웹, 프론트엔드, 백엔드, 데이터 분석, fastapi 등). 링크 자료에는 PM 표의 tags 순서를 그대로 두고 **뒤에 한글 별칭만 추가**(link_008 넥스트·리액트, link_009 테일윈드, link_012 노드·자바스크립트, link_013 익스프레스, link_017 포스트그레스, link_019 고, link_021 씨샵·닷넷, link_022·023·024 파이썬(024 사이킷런), link_026 파이썬·자바스크립트·js, link_027 파이썬, link_029 깃). URL, 제목, 조각은 변경 없음. 별칭 사전 코드는 만들지 않았다 | `backend/data/rag_documents.json` |
| R3 | 2글자 영문 분야는 막되 허용 목록(`ai`, `ui`, `ux`, `db`, `qa`)은 정확히 일치할 때 허용. 목록 밖("go", "qq", "js")과 1글자는 계속 매칭 없음. 막힌 분야라도 과정 토큰 보완 매칭은 동작한다 | `resources_catalog.py` |
| 계약 문서 | `docs/phase1_design.md` references 행에 보완 매칭 규칙 한 줄 추가. DTO 변경은 없다 | |

## §1 표 입력의 전후 결과 (자료 id)
| 입력(field / course) | 수정 전 (67d0a46) | 수정 후 |
|---|---|---|
| VIBE CODING / 웹 개발의 기초 | (빈 결과) | link_004, link_010, link_001, link_002, link_003 |
| VIBE CODING / 웹 개발 | (빈 결과) | link_004, link_010, link_001, link_002, link_003 |
| 웹 개발 / 기초 | link_001, link_002, link_003, link_004, link_005 | link_004, link_010, link_001, link_002, link_003 |
| 웹 개발의 기초 / (빈 과정) | link_001, link_002, link_003, link_004, link_005 | link_004, link_010, link_001, link_002, link_003 |
| 프론트엔드 개발자 / 웹 개발의 기초 | link_001, link_002, link_003, link_004, link_005 | link_004, link_010, link_001, link_002, link_003 |
| 파이썬 / 기초 | (빈 결과) | doc_001, doc_002, doc_003, doc_009, link_022 |
| 파이썬 개발 / 자료구조 | (빈 결과) | doc_002, doc_001, doc_003, doc_009, link_022 |
| 자바스크립트 / 기초 | (빈 결과) | doc_004, doc_005, doc_010, link_012, link_026 |
| AI / 머신러닝 | (빈 결과) | link_025 |
| 영어 회화 | link_030, link_031 | link_030, link_031 |
| Java | link_014, link_015 | link_014, link_015 |
| Docker | link_016 | link_016 |
| 데이터 분석 | link_022, link_023, link_024, doc_006, link_018 | link_022, link_023, doc_006, link_024, link_018 |
| 백엔드 개발 / Spring | link_015, link_014, link_012, link_013, link_016 | link_015, link_014, link_012, link_013, link_019 |
| 요리 / 한식 | (빈 결과) | (빈 결과) |
| UX 디자인 / SQL 기초 | (빈 결과) | doc_006, link_018, link_017 |
| 개발 / 입문 | (빈 결과) | (빈 결과) |

정상이던 입력의 순서가 바뀐 곳(의도한 부작용, 확인 요청):
- **웹 개발** 계열: 동점 처리(앞쪽 tag 우선) 때문에 link_004(web.dev), link_010(Odin Project)이 위로 오고 link_005(TypeScript)가 5위 밖으로 빠졌다. 웹 개발 입문에는 두 자료가 더 어울린다고 판단했으나 PM 이 tags 순서를 바꿔 조정할 수 있다.
- **백엔드 개발 / Spring** 5번째가 link_016(Docker)에서 link_019(Go)로 바뀌었다(Docker 의 `백엔드` tag 가 뒤쪽이라서). Docker 가 더 유용해 보이니 필요하면 link_016 tags 의 `백엔드` 위치를 앞으로 옮기면 된다(데이터 수정만).
- 데이터 분석에서 doc_006(SQL)이 link_024 앞으로 왔다.

## 바뀐 기대값 목록
| 테스트 | 이전 기대 | 새 기대 | 이유 |
|---|---|---|---|
| `test_resources_catalog.py::two_character_field…` | "AI" → 빈 결과 | "AI" → link_025 만, "go"/"qq" 는 빈 결과 | R3 허용 목록 |
| `test_phase6c.py` 짧은 영문 분야 | "AI" → 없음 | "AI" → link_025, "go"/"QQ" 없음 | R3 |
| `test_phase6c.py` 모호한 분야·과정만으로 매칭 금지 | ("AI","") 빈 결과 포함, ("우주공학","html") 빈 결과 | ("요리","한식") 로 교체 | 과정 "html" 은 이제 도메인 단어라 웹 자료가 나오는 것이 새 규칙 |
| `test_phase6c.py` 기존 10건 tags | "tags 없음" | "tags 있음, verified_at 그대로" | R2 |
| `test_phase6c.py` 정렬 검증 | (점수, id) | (점수, 첫 tag 위치, id) | 새 동점 규칙 |
| 신규: UX 디자인 / SQL 기초 | (빈 결과) | doc_006, link_018, link_017 | 지시서가 예고한 변경. "UX 디자인 / 기초"는 계속 빈 결과 |
- 무관 사례("요리 / 한식")는 계속 빈 결과, "Java ≠ JavaScript"(분야·과정 보완 양쪽), 일반어만 있는 입력의 빈 결과, 분야가 맞을 때 과정이 자료를 끌어오지 않는 규칙("Java / 웹 개발"에 웹 자료 없음)은 테스트로 유지·추가했다.

## PM 확인 요청에 대한 답
- **최종 불용어 목록:** 개발, 개발자, 기초, 입문, 코딩, 학습, 공부, 과정, 기본, 초급, 강의, development, developer, basic, basics, beginner, coding, study, course, learn (+ 한글 일반어에 조사가 붙은 형태). 테스트(`test_stopword_list_is_the_documented_one`)로 고정했다.
- **"coding"/"코딩" 을 도메인 토큰에서 제외해도 되는지:** 제외해도 된다. 이유는 link_026(생활코딩)의 tags 에 "코딩" 이 있지만, "코딩" 만으로 어떤 학습이든 생활코딩에 붙으면 오매칭이기 때문이다. 과정 보완 매칭에서도 "코딩 학습", "개발의 기초" 등은 빈 결과임을 테스트했다.
- **Python 학습에 pandas 가 함께 나오는 순서:** Python 자료가 위(`파이썬 / 기초`, `Python 개발 / 기본문법` 모두 doc_001~003 이 상위, pandas 는 있어도 doc_001 아래).

## 테스트
- 새 26건: 과정 보완(자유 분야 ×2, 이미 맞는 분야 ×3, 분야 우선, 일반어만이면 빈 결과, 영문 완전 일치, 무관 사례, 1글자 "웹", UX/SQL), 한글 별칭(파이썬, 자바스크립트, 깃, 넥스트, 리액트, 노드, 도커, 자바 ≠ 자바스크립트, tags 순서 보존, 모든 자료에 tags), 짧은 영문 허용 목록, 조사가 붙은 일반어, 튜터 `related_links` 와 references API(자유 분야 학습).
- backend 전체 **623 통과**.

## 미검증
- 실제 서버에서 튜터(실제 AI)의 `related_links`(PM 확인 예정). 브라우저 화면(프론트 변경 없음).
- 한글 별칭이 없는 입력(예: "리액트 네이티브", "플러터")은 계속 매칭되지 않는다(정밀도 우선). 사용자 테스트에서 자주 나오는 입력은 tags 로 추가하면 된다.

## 열린 결정
1. 웹 개발 계열 순서(link_004, link_010 우선), Spring 5번째(Go vs Docker)를 위처럼 둘지(데이터 수정으로 조정 가능).
2. 과정 보완 매칭은 분야가 **하나도** 안 맞을 때만 동작한다. 분야가 일부만 맞는데(예: "VIBE CODING 파이썬") 과정이 더 정확한 경우는 분야 매칭 결과를 따른다. 필요하면 두 방식을 합치는 규칙을 PM 이 정한다.

## 커밋에 포함하지 않은 것
`frontend/AGENTS.md`.
