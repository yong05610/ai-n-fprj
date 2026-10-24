# Phase 6B 수정 2 보고서 (R4) — 인사이트 재시도 비용과 502

작성: 개발팀, 2026-10-24. 기준: docs/phase6b_fix_instructions_2.md. Phase 7 과 6C 는 시작하지 않았다.

## 요약
- R4-1~R4-4 구현 완료. backend pytest **539 통과**(기존 518 + 새 21). 프론트는 변경 없음(typecheck, npm test 통과, build 는 프론트 무변경이라 다시 하지 않음 → 미검증).
- 개발팀 실제 AI 측정(PM 과 같은 데이터, 서로 다른 사용자 5명): **성공 5/5, 모델 호출 평균 1.0회, 502 0회**. 목표(502 = 0, 평균 ≤ 1.2) 충족.

## 변경 내용
| 항목 | 내용 | 파일 |
|---|---|---|
| R4-1 | `reflection_used < 2` 이면 `AIInsightBasic`(summary, next_action)과 `INSIGHT_SYSTEM_PROMPT_BASIC` 을 쓴다. 이 프롬프트에는 "difficulty" 라는 단어가 없고 "이번 요청은 summary 와 next_action 만 출력한다."가 있다. 저장 difficulty 는 `""`. 2건 이상이면 기존 `AIInsight` 와 프롬프트 그대로 | `backend/prompts.py`, `ai_schemas.py`, `main.py` |
| R4-2 | R2 서버 검증은 그대로. `AIInsightBasic` 에도 `difficulty` 필드(기본 "")를 남겨, 모델이 몰래 보낸 값이 조용히 버려지지 않고 R2 안전망에서 거부되게 했다 | `ai_schemas.py` |
| R4-3 | 거부될 때마다 INFO 한 줄 `insight_validation_reject reason=<…> attempt=<n>`. reason: difficulty_without_reflections / quantity / forbidden_term / empty_part / length / other(시간 초과·JSON 오류 포함). 입력·회고·AI 원문·숫자·UID 는 넣지 않음 | `ai_client.py`(`on_reject` 콜백, `AIRetryFeedback.reason`), `main.py` |
| R4-4 | 프롬프트 공통 끝부분에 "목표 대비 진행을 '부족하다/모자라다/미달' 같은 평가 어조로 쓰지 않는다. 제공된 숫자와 사실만 전한다" 추가. 금지 표현 목록은 그대로 | `prompts.py` |

바꾸지 않은 것: 금지 표현 목록, 숫자 검증 규칙, API 계약, 프론트, 재시도 횟수(MAX_RETRIES=2).

## 테스트 (`backend/tests/test_phase6b_fix2.py`, 21건)
- 기본 프롬프트에 difficulty 없음 / 전체 프롬프트에는 있음 / 두 프롬프트 모두 숫자·어조 규칙 포함
- 회고 1건: 기본 프롬프트 사용, 모델 호출 1회, 저장 difficulty "". 회고 2건: 전체 프롬프트, difficulty 유지. 요청마다 프롬프트를 새로 고름
- 가짜 AI 가 difficulty 를 보내도 회고 1건이면 3회 모두 거부, 502, 저장 없음(R2 안전망). 오류 메시지 그대로
- 로그: 사유별(quantity, forbidden_term, empty_part ×2, length, other) 한 줄 형식, 시간 초과는 other. 성공 시 로그 없음
- `caplog` 로 앱 로그(`pacemate*`)에 요약 원문, "4시간 53분", UID, goal id, 회고 원문이 없음을 확인. (테스트 클라이언트 자체의 httpx 로그에는 URL 의 goal id 가 찍히는데 이는 앱 로그가 아니다)
- 결과: 전체 539 통과, 프론트 npm test 통과(typecheck 통과)

## 개발팀 실제 AI 측정 (dev 모드, 메모리 저장소, 포트 8123, 측정 후 서버 종료 확인)
데이터: 기록 4건(30, 31, 32, 20 = 113분), 회고 1건("for 문과 while 문 차이가 아직 헷갈린다"), 주 7시간. 사용자 5명 각각 1회 호출. 모델 호출 수는 모델 클라이언트를 감싸 시도마다 1줄을 센 값이다(내용 기록 없음).

| 사용자 | HTTP | 모델 호출 | 승인되지 않은 시간·건수 표현 | difficulty | 올바른 합계("1시간 53분" 또는 "113분") 언급 |
|---|---|---|---|---|---|
| 1 | 201 | 1 | 없음 | 빈 값 | 예 |
| 2 | 201 | 1 | 없음 | 빈 값 | 예 |
| 3 | 201 | 1 | 없음 | 빈 값 | 예 |
| 4 | 201 | 1 | 없음 | 빈 값 | 예 |
| 5 | 201 | 1 | 없음 | 빈 값 | 예 |

- 성공 5/5, 평균 모델 호출 **1.0**, 502 **0**. 서버 로그에 `insight_validation_reject` 한 줄도 없었다(거부 0건). 로그에 사용자 id("qa-r4")와 회고 문구도 없었다.
- 어조(R4-4): 응답 문장 자체는 보고서와 로그에 남기지 않는 원칙이라 개발팀은 "부족/미달" 사용 여부를 자동 검사하지 않았다 → **미검증**(PM 확인 필요).

## 한계와 솔직한 메모
- 표본이 5회다. 502 가 0회였다고 확률이 0 이라는 뜻은 아니다. 이전 PM 측정의 502 한 건은 사유를 알 수 없었고, 이번에는 거부 자체가 없어 R3 판단 자료(사유별 빈도)는 아직 쌓이지 않았다. R4-3 로그가 운영 중 이를 쌓는다.
- 회고 2건 이상 경로의 실제 AI 측정은 하지 않았다(지시 범위 밖). 그 경로는 이전과 같다.
- 한글 숫자("두 시간")와 "N개" 표현의 검증 빈틈은 지시대로 수용했다.
- 커밋에 포함하지 않은 파일: `backend/tutor.py`(내가 만들지 않은 빈 줄 변경), `서비스기획서.md`, `frontend/AGENTS.md`.

## 미검증
- 프론트 build(무변경), Firebase 모드 인사이트 저장, 브라우저 화면, 회고 2건 이상의 실제 AI 응답, 응답 어조.
