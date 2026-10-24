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
