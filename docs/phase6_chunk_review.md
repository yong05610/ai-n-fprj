# Phase 6 자료 조각 검토 (PM, 2026-10-23)

**대상:** backend/data/rag_chunks.json 의 10개 문서 × 53개 조각(전부 verified: false)
**방법:** 53개 조각을 하나씩 읽고, 해당 자료(Python 공식 튜토리얼, MDN, W3Schools, Git Book, Next.js, FastAPI, javascript.info)의 내용과 대조했다. 대조 기준은 PM 이 아는 공식 문서의 사실이며, 원문 페이지를 열어 문장 단위로 비교한 것은 아니다. 확인한 점: (1) 사실 오류 여부, (2) 원문 복사 여부(전부 한국어 요약), (3) 자료 범위를 벗어난 내용이 없는지, (4) 키워드가 본문과 맞는지.

## 결과: 53개 전부 승인

| 문서 | 승인 조각 | 비고 |
|---|---|---|
| doc_001 Python 기본 문법 | c1 c2 c3 c4 c5 | `/` 는 항상 실수, `//` 몫, 문자열 불변 등 정확 |
| doc_002 Python 자료구조 | c1 c2 c3 c4 c5 c6 | 빈 집합 `set()`, 리스트 큐는 느려 deque 권장 정확 |
| doc_003 Python 함수 | c1 c2 c3 c4 c5 | 기본값은 정의 시점 1회 계산, None 패턴 정확 |
| doc_004 MDN JS 기초 | c1 c2 c3 c4 c5 | let/const, `===`, addEventListener 정확 |
| doc_005 MDN 비동기 JS | c1 c2 c3 c4 c5 | Promise.all 하나라도 거부되면 거부 정확 |
| doc_006 SQL 기초 | c1 c2 c3 c4 c5 c6 | LIMIT(MySQL)/TOP(SQL Server), UPDATE·DELETE WHERE 주의 정확 |
| doc_007 Git | c1 c2 c3 c4 c5 | 스냅샷, 세 영역, fetch 와 pull 의 차이 정확 |
| doc_008 Next.js App Router | c1 c2 c3 c4 c5 | 서버 컴포넌트 기본, "use client", page 와 route 동시 불가 정확 |
| doc_009 FastAPI | c1 c2 c3 c4 c5 c6 | /docs, /redoc, 422, Depends, CORSMiddleware 정확 |
| doc_010 javascript.info | c1 c2 c3 c4 c5 | 자료형 8가지, 클로저, 프로토타입 정확 |

개발팀은 위 53개 id 를 모두 `verified: true` 로 바꾼다. 조각 id 는 `doc_00N_cM` 형식이며 표의 문서 번호와 조각 번호 조합이다.

## 알려진 한계 (승인을 막지는 않음)
- 조각 길이가 113~206자로 지시서의 "300자 안팎"보다 짧다. 정확성을 우선한 판단을 받아들인다. 더 길게 늘리지 않는다.
- 자료에 없는 분야(React, Docker 등)는 검색 결과가 비어 "참고한 등록 자료가 없어요"로 답한다. 의도된 동작이다.
- 서로 다른 언어의 같은 단어가 점수를 만든다. 예: "git push" 질문에 JavaScript 배열 `push` 조각(doc_004_c3)이 2순위로 따라온다. 모델이 `used_source_ids` 로 실제 쓴 자료만 고르므로 출처 오표시 위험은 낮지만, 사용자 테스트에서 이상한 출처가 보이면 6B 이후 가중치를 조정한다.
