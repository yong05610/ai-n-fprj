# Phase 6C(학습 자료 접근성) 검증 결과 (PM, 2026-10-25)

**대상:** 커밋 67d0a46, 지시서 docs/phase6c_dev_prompt.md, 개발팀 보고 docs/phase6c_report.md
**판정:** 링크 자료 데이터·검색 링크·튜터 키워드는 승인(dev 모드). **분야 매칭에 수정 필요**(docs/phase6c_fix_instructions.md). 화면 동작과 Firebase 실연동은 PM 미검증.

## 1. 직접 확인한 것
- backend `pytest` **597 passed**, frontend `typecheck` 통과, `npm test` **72 passed**, `npm run build` 통과(보고와 일치).
- **데이터:** `rag_documents.json` 41건(기존 10 + 링크 31). 링크 자료는 PM 목록(docs/phase6c_resource_links.md)과 **id, 제목, URL 이 모두 일치**(불일치 0건), `chunks` 비어 있음, `verified: true`, `verified_at: 2026-10-24`, 라이선스 "링크만 제공(원문 복제 없음)".
- **검색 링크(`search_links`):** 구글·공식 문서·유튜브 3개, 고정 템플릿과 퍼센트 인코딩, 라벨 "(검토 전 외부 링크)". AI 출력과 클라이언트 URL 은 쓰지 않음(코드 확인).
- **분야 매칭 시험(`match_references`):** 영어 회화, Java, Docker, 데이터 분석, 백엔드/Spring, 웹 개발류는 기대대로. 무관 입력(요리/한식, 개발/기초, UX 디자인/기초)은 빈 결과. **다음은 기대와 다름(수정 지시 R1~R3):** VIBE CODING/웹 개발의 기초(실제 테스트 학습), 파이썬/기초, 자바스크립트/기초, AI/머신러닝.
- **실제 서버(실제 OpenAI 2회, dev + memory):** 출처 없는 질문(영어 말하기 학습법) → `search_keywords` 3개와 "더 찾아볼 키워드" 줄, 출처 비어 있음, "참고한 등록 자료가 없어요" 부착. 출처 있는 질문(파이썬 리스트 append) → 출처 1건, 키워드 없음. 두 응답 모두 `related_links` 가 빈 목록이었다(테스트 학습이 자료와 매칭되지 않아서, R1 의 영향).
- 주간 계획 참고자료 API: VIBE CODING/웹 개발의 기초 학습에서 `references` 는 빈 목록, `search_links` 3개.

## 2. 미검증
- 화면(주간 계획의 "직접 검색해 보기", 튜터의 키워드 줄·"함께 보면 좋은 자료")은 개발팀 보고만 있음, 모바일 폭, Firebase 실연동, 링크가 배포 시점에도 열리는지(PM 은 2026-10-24 에 확인, 배포 직전 재확인 필요: docs/pre_deploy_checklist.md).

## 3. 개발팀 열린 결정 처리
불용어 추가 승인(최종 목록 보고), Python 에 pandas 등 데이터 자료 허용, 한글 짧은 분야 허용 승인, 한글 별칭은 tags 로 해결(R2), 짧은 영문 분야는 허용 목록 권고(R3). 상세는 수정 지시서 §5.

## 4. 수정 재검증 (2026-10-25, 커밋 6abf810)
- backend `pytest` **623 passed**(직전 597 + 26). 프론트는 변경 없음.
- `match_references` 직접 시험(수정 전 → 후): **VIBE CODING / 웹 개발의 기초** 빈 결과 → 웹 링크 5건(web.dev, The Odin Project, MDN HTML·CSS·HTTP), 파이썬 / 기초 빈 결과 → Python 자료 5건(doc_001~003 이 위), 자바스크립트 / 기초 빈 결과 → JavaScript 자료(doc_004, doc_005, doc_010, ...), AI / 머신러닝 빈 결과 → link_025. 무관 입력(요리/한식, 개발/기초, 개발/입문, 운동/헬스, XY/기초)은 계속 빈 결과, 기존 정상 입력(영어 회화, Java, Docker, 데이터 분석, Python 개발)은 유지. 실제 서버: 테스트 학습(VIBE CODING/웹 개발의 기초)의 참고자료 API 에서 `references` 5건과 `search_links` 3개.
- 알려진 차이(수용): "UX 디자인 / SQL 기초" 가 SQL 자료를 찾게 되었다(과정 보완 매칭의 새 규칙, 지시서가 예고). "백엔드 개발 / Spring" 5위가 Docker 에서 Go 로 바뀜(Docker 가 더 유용하나 영향 작음, 필요 시 tags 순서로 조정). "Go / 언어" 는 2글자 영문이라 매칭되지 않음(허용 목록에 `go` 가 없음, 영향 작음, 필요 시 허용 목록에 추가). 웹 개발 순위에서 TypeScript 가 5위 밖으로 밀림(수용).
- **새로 발견한 설계 결함(PM 지시서):** 튜터 `related_links` 가 출처가 있는 답변에서만 나오도록 지시했기 때문에, 출처가 거의 없는 실제 질문에서는 학습에 맞는 검토된 링크가 튜터에 보이지 않는다(실제 AI 호출로 확인). → `docs/phase6c_fix_instructions_2.md` R4.
- 판정: **6C 수정(R1~R3) 승인(dev 모드).** R4 후 6C 전체를 마무리한다. TASK C6.2 는 승인으로 체크, C6.3·C6.4 는 화면 확인 뒤 체크.
