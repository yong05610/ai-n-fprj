# Phase 6C 수정 2 보고서 — 튜터 "함께 보면 좋은 자료"를 출처 유무와 무관하게

작성: 개발팀, 2026-10-25. 기준: docs/phase6c_fix_instructions_2.md (대상 커밋 6abf810). Phase 5F, 7 은 시작하지 않았다.

## 요약
- R4 구현 완료. backend pytest **637 통과**(수정 전 623 + 새 14: `test_phase6c_fix2.py`, 기존 1건 기대값 수정). 프론트 코드 변경 없음.
- PM 시나리오(학습 VIBE CODING / 웹 개발의 기초, 질문 "HTML과 CSS는 각각 무슨 역할이에요?", 출처 없음)에서 `related_links` = **web.dev: 웹 개발 학습하기, MDN: HTML 구조 만들기** 2건. 실제 AI 호출은 하지 않았다(서버가 만드는 값, 브라우저 확인은 가짜 AI).

## 변경 내용
| 항목 | 내용 | 파일 |
|---|---|---|
| R4-1 | `related_links` 를 출처 유무와 무관하게 만든다. 거절된 답변(`refused`)과 비-assistant 메시지는 빈 목록. 현재 학습(active_goal_id, 진행 중)과 `match_references` 로 매칭된 자료 중 이미 출처인 자료를 빼고 최대 2건 | `backend/tutor.py` (`decorate`, `related_links_for`) |
| R4-2 | **질문과 겹치는 링크를 앞에**: 질문 토큰(`rag.topic_tokens`)과 링크의 `tags`·제목 토큰이 **정확히 같은** 개수가 많은 순(안정 정렬: 동점·겹침 없음은 기존 매칭 순서). 서버만 결정하며 AI 출력은 링크에 쓰이지 않는다(테스트: 가짜 AI 가 `related_links` 필드와 URL 을 보내도 응답의 URL 은 모두 카탈로그 값) | `backend/tutor.py` (`_question_overlap`) |
| 질문 전달 | 답변을 꾸밀 때 그 답변 앞의 사용자 메시지를 질문으로 쓴다: 새 답변(질문 원문), 멱등 재요청(저장된 짝의 질문), 대화 상세 조회(각 답변 바로 앞 질문) | `backend/main.py` (`_decorated_messages`, `send_message`) |
| R4-4 | 저장하지 않고 응답 때 만드는 방식 유지(저장 필드는 `search_keywords` 뿐, 테스트로 확인) | |
- 변경하지 않은 것: 다른 매칭 규칙, 링크 자료, AI 프롬프트·스키마, 프론트 컴포넌트, API/DTO(필드는 6C 에서 이미 있음 → 계약 문서 변경 없음).
- 동작 변화: 이전에는 `search_keywords` 가 있으면 `search_links` 만, 출처가 있으면 `related_links` 만 만들었다. 이제 `search_links`(키워드 있을 때)와 `related_links`(항상)가 함께 나온다.

## 시나리오별 결과 (학습 VIBE CODING / 웹 개발의 기초, 제목만)
| 질문 | related_links |
|---|---|
| HTML과 CSS는 각각 무슨 역할이에요? | web.dev: 웹 개발 학습하기, MDN: HTML 구조 만들기 |
| css 에서 색상을 바꾸는 방법 | web.dev: 웹 개발 학습하기, MDN: CSS 스타일링 기초 |
| html 태그 종류 | web.dev: 웹 개발 학습하기, MDN: HTML 구조 만들기 |
| http 요청이 뭐예요 | MDN: HTTP, web.dev: 웹 개발 학습하기 |
| 동기를 유지하는 요령이 있을까요? (겹침 없음) | web.dev: 웹 개발 학습하기, The Odin Project: 웹 개발 커리큘럼 (기존 매칭 순서) |
- **PM 확인 요청:** "HTML과 CSS" 질문에서 web.dev 가 1위인 이유는 그 링크의 tags 에 `html` 과 `css` 가 둘 다 있어 겹침이 2이기 때문이다(MDN HTML·CSS 는 각 1). 2건 제한 때문에 **MDN CSS 는 밀려난다**. PM 이 "MDN HTML·CSS 가 앞에"를 기대했다면 web.dev 의 tags 에서 `html`, `css` 를 빼거나, 겹침 수 대신 "겹치는지 여부"로만 정렬하게 바꾸는 방법이 있다(후자도 web.dev, MDN HTML 이 앞이라 결과는 같다). 어느 쪽이든 데이터/규칙 한 줄 수정이라 지시를 주면 바로 한다.

## 테스트
- 새 14건(`test_phase6c_fix2.py`): PM 시나리오(출처 없음, 키워드 있음, 링크 순서·URL 값), CSS 만/HTML 만/HTTP 질문의 순서, 겹침 없음은 기존 순서, 출처 자료 제외, 거절된 질문·매칭 없는 학습("요리/한식")·학습 없음은 빈 목록, 최대 2건, 저장 안 함, 대화 상세와 멱등 재요청이 각 질문 기준으로 같은 링크, 정확 일치 규칙(`java` ≠ `javascript`), AI 가 보낸 링크 필드 무시.
- 기존 1건 수정: `test_phase6c.py` "출처 없는 답변…" 의 `related_links == []` → 1~2건(새 규칙).
- backend 전체 **637 통과**. 프론트는 변경이 없어 typecheck·test·build 를 다시 돌리지 않았다.

## 화면 확인 (실제 Chrome, 가짜 AI, dev + memory, 빈 포트 8123/3123)
- 학습 VIBE CODING / 웹 개발의 기초, 질문 "HTML과 CSS는 각각 무슨 역할이에요?": 말풍선에 "더 찾아볼 키워드" 줄, "참고한 등록 자료가 없어요" 안내, "직접 검색해 보기" 링크 3개. 우측 패널은 "참고한 자료가 없어요" 아래에 **"함께 보면 좋은 자료" 2건(web.dev, MDN HTML)**, 그 아래에 "직접 검색해 보기" 3개와 "검토 전 외부 링크예요." 순서로 어색함 없이 표시됨. 레이아웃 조정 없음 → 프론트 변경과 목업 대조표 갱신 없음.
- 말풍선 하단에는 6C 와 같이 검색 링크만 있고, 관련 자료는 우측 패널에만 표시한다(지시서 §1-D 의 구현 위치 그대로).
- 서버 두 개 모두 종료 확인.

## 미검증
- 실제 AI 를 붙인 서버에서의 확인(PM 예정). Firebase 모드에서의 대화 상세 조회(코드는 저장소 추상화만 사용). 모바일 폭 화면.

## 열린 결정
- 위 "PM 확인 요청"의 정렬 기준(겹침 개수 vs 겹침 여부)과 web.dev tags 조정.

## 커밋에 포함하지 않은 것
`frontend/AGENTS.md`.
