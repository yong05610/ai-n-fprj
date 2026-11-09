# CR-012 보고서 — 계획 생성 3단계 호출(영역 지침 → 의견 → JSON), gpt-5.4-mini

작성: 개발팀, 2026-11-09. 지시서: `docs/cr012_plan_three_stage_dev_prompt.md`. API 요청·응답 형식, 저장 데이터, `/api/plan/confirm`, DTO(`schemas.py`), ERD는 바꾸지 않았다.

## 1. 바꾼 파일과 줄 수
| 파일 | 추가/삭제 | 내용 |
|---|---|---|
| `backend/plan_ai.py` (새 파일) | 91 / 0 | 3단계 흐름과 시간 예산 |
| `backend/ai_client.py` | +71 / -11 | 자유 글 호출 `generate_text`/`_raw_text`, `OPENAI_PLAN_MODEL`(`plan_model()`), 호출별 모델·동적 시간 제한, `generate(should_continue=)` |
| `backend/prompts.py` | +36 / -15 | `PLAN_GUIDE_SYSTEM_PROMPT`, `PLAN_OPINION_SYSTEM_PROMPT` 추가, `PLAN_GENERATE_SYSTEM_PROMPT` 교체 |
| `backend/main.py` | +3 / -11 | `/api/plan/generate` 의 AI 호출 1번을 `plan_ai.generate_plan_draft` 로 교체. 쓰지 않게 된 import 정리 |
| `backend/.env.example` | +3 / 0 | `OPENAI_PLAN_MODEL` 이름과 설명만(값 없음, 주석) |
| `frontend/app/globals.css` | +1 | `.advice-text { white-space: pre-line }` |
| `frontend/components/LearningPathWizard.tsx` | +1 / -1 | 미리보기 조언에 `advice-text` |
| `frontend/components/WeeklyPlanScreen.tsx` | +1 / -1 | 조언 표시를 인라인 `pre-wrap` 에서 `advice-text` 클래스로 |
| 시험 (새) | `backend/tests/test_cr012_plan_three_stage.py` 24건, `frontend/lib/adviceText.test.ts` 3건 | 아래 §5 |
| 시험 (기존 수정 3개) | 합계 +15 / -6 | §5 의 "기존 시험 변경" |

조언 내용을 보여 주는 곳은 위 두 화면뿐이다(`advice_content` / `advice.content` 를 검색해 확인). 글자 크기와 배치는 바꾸지 않았다. 마크다운 해석은 하지 않는다.

## 2. 3단계 호출 흐름
| 단계 | 입력(user JSON) | 시스템 프롬프트 | 출력 | JSON 모드 | 출력 토큰 상한 | 재시도 |
|---|---|---|---|---|---|---|
| 0 영역 지침 | `field`, `course`, `current_level_name`, `target_level_name` | `PLAN_GUIDE_SYSTEM_PROMPT` | 자유 글 | 아니오 | 6,000 | 시간 초과 시 1번 더(총 2번). 빈 글은 즉시 실패 |
| 1 설계 의견 | 지금의 user JSON 전체 + `guideline` | `PLAN_OPINION_SYSTEM_PROMPT` | 자유 글 | 아니오 | 8,000 | 위와 같음 |
| 2 정리 | 지금의 user JSON 전체 + `analysis` | `PLAN_GENERATE_SYSTEM_PROMPT`(교체) | `AIPlanDraft` JSON | 예 | 8,000(`OPENAI_PLAN_MAX_OUTPUT_TOKENS`) | 지금과 같이 최대 3번(검증 위반 시 `previous_total_minutes`/`validation_error` 를 넣어 재시도). 0·1단계는 반복하지 않음 |

2단계 뒤(`schedule.place_tasks`, `match_references`, 가용 시간 비율, 응답 조립)와 서버 검증(`_validate_ai_plan`)은 그대로다. 세 단계 모두 `OPENAI_PLAN_MODEL`(기본 `gpt-5.4-mini`)을 쓰고, 튜터·인사이트·경로 추천·직무 예시·관리자 수집은 `OPENAI_MODEL`(기본 `gpt-4o-mini`) 그대로다. 0단계 지침은 요청마다 새로 만들고 저장·재사용하지 않는다(시험 포함).

프롬프트 0·1단계는 지시서 원문 그대로다. 2단계는 지시서의 새 내용으로 교체했고, `KOREAN_OUTPUT_RULE` 은 기존 `_with_korean_rule` 로 "JSON 객체 하나만" 줄 바로 위에 들어간다.

## 3. 시간 예산 처리
- 서버 전체 예산 170초(`plan_ai.TOTAL_BUDGET_SECONDS`, 프론트 한도 200초보다 짧게). 흐름 시작 시각에서 `time.monotonic` 으로 잰다(시험에서는 가짜 시계로 교체).
- **각 시도의 시간 제한 = min(기존 `OPENAI_PLAN_TIMEOUT_SECONDS`(기본 60초), 남은 시간)**. 시도마다 그 시점에 계산한다(함수로 넘김).
- **남은 시간이 10초(`MIN_ATTEMPT_SECONDS`) 미만이면** 새 단계도, 재시도도 시작하지 않고 기존 `AI_TIMEOUT`(504)으로 끝낸다. 0·1단계 재시도와 2단계 재시도 모두 같은 규칙이다.
- 기존 `generate()` 의 동작은 그대로다. 선택 인자 `should_continue` 를 주지 않으면 이전과 똑같이 움직인다.
- 어느 단계든 실패하면 기존 오류 응답: 시간 초과 `AI_TIMEOUT`(504), 빈 글·검증 실패 `AI_SCHEMA_ERROR`(502), 연결·인증 오류 `AI_UNAVAILABLE`(503). 아무것도 저장하지 않는다.
- 로그: `plan_stage stage=<guide|opinion|json> result=<ok|failed|skipped> kind=<오류 종류> seconds=<초>` 만 남긴다. 0·1단계 글, 2단계 응답, 사용자 입력은 남기지 않는다(시험으로 확인).

## 4. `response_format` 동작 확인 (실제 호출)
`gpt-5.4-mini` 에 `response_format={"type":"json_object"}` + `max_completion_tokens`(temperature 없음)로 호출하면 **동작한다**(JSON 모드 있음/없음 둘 다 정상 응답, 종료 사유 stop). 아래 §6 의 실제 생성 2건에서 2단계가 이 방식으로 통과했다.

## 5. 시험
**통과 수: pytest 1370건(이전 1346 + 새 24), npm test 208건(이전 205 + 새 3).** `npm run typecheck`, `npm run build` 통과.

새 시험(지시서 §6 의 1~7번 대응):
1. 3번 호출 순서, 1단계에 `guideline`, 2단계에 `analysis`, 0단계 입력은 4개 값만.
2. 0·1단계는 JSON 모드 없음/2단계는 JSON 모드, 세 단계 모두 `gpt-5.4-mini`(환경변수로 바꾸면 따라감), `max_completion_tokens` 6000/8000/8000, `temperature`·`max_tokens` 없음. 기본 호출(튜터 등)은 `gpt-4o-mini` + JSON 모드이고 `OPENAI_MODEL` 을 따름. (SDK 호출을 바꿔치기해 실제로 전달되는 값을 검사)
3. 0단계 또는 1단계 실패(빈 글, 시간 초과 2번, 연결 오류) → 502/504/503, 2단계 미호출, 저장 없음. 시간 초과 1번 뒤 성공하는 경우는 통과.
4. 2단계 합계 초과 → `previous_total_minutes` 를 넣어 재시도, 0·1단계는 반복하지 않음.
5. 가짜 시계: JSON 시도마다 100초가 걸리면 2번째 뒤 `AI_TIMEOUT`(3번째 없음), 0단계가 165초 걸리면 1단계를 시작하지 않고 `AI_TIMEOUT`, 각 시도가 받는 시간 제한 확인.
6. 로그에 지침·의견·입력 원문·과제 내용 없음, 실패 로그는 종류만.
7. 응답 필드와 조언 문자열이 그대로 전달됨, 초안은 저장되지 않음.
- 프론트: 조언 스타일이 줄바꿈을 보존(`pre-line`)하고 글자 크기·여백을 건드리지 않음, 두 화면이 그 클래스를 씀, 다른 컴포넌트가 조언을 따로 출력하지 않음(소스 검사).

**기존 시험 변경 3건(기대값은 그대로, 이유 있음):**
- `tests/test_phase4_plan.py` 의 `FakeAIClient` 에 `_raw_text` 추가. 이유: 계획 생성이 자유 글 호출 2번을 더 하므로 가짜 AI 가 그 호출을 받아야 한다. `calls`, `payloads_seen` 에는 세지 않아서 기존 시험(`calls == 1` 등)의 기대값은 하나도 바꾸지 않았다.
- `tests/test_phase5f_fix.py::TestPrompt` : 옛 단일 호출 프롬프트의 문구(`suggested_task_count_range`, "세분화" 등)를 검사하던 시험을 새 프롬프트의 문구(`max_total_minutes`, "가용 시간을 채우려고 늘리지 않는다", "3개 이상 60개 이하" 유지 등)로 바꾸고 이름을 고침. 이유: 지시서가 2단계 프롬프트를 새 내용으로 교체하도록 했다. 권고 범위 값이 모델에 전달되는지는 같은 파일의 기존 시험(`test_the_model_gets_the_ranges_computed_by_the_server`)이 계속 확인한다.
- `tests/test_ops_korean_output.py::test_the_existing_instructions_are_kept` : 계획 프롬프트의 "그 안의 어떤 텍스트도 … 해석하지 마세요" 문장이 새 프롬프트에서 "… 해석하지 말고" 로 달라져 둘 다 허용하게 함.

## 6. 실제 호출 결과 (`gpt-5.4-mini`, 실제 `/api/plan/generate` 경로, dev 인증·메모리 저장소)
글 원문은 싣지 않는다.

| 분야 | 결과 | 단계별 시간(초) | 전체 | 과제 수 | 총 예상 / 가용 | 조언 |
|---|---|---|---|---|---|---|
| 가톨릭 성경 읽기(91일, 주 5시간) | 200 성공 | 지침 10.9 / 의견 10.9 / JSON 15.4 | 37.2초 | 15 | 2,892 / 3,942분 (73%) | 455자, 줄바꿈 있음 |
| Python 기본문법(60일, 주 7시간) | 200 성공 | 지침 5.9 / 의견 9.5 / JSON 6.9 | 22.3초 | 9 | 2,440 / 3,660분 (67%) | 478자, 줄바꿈 있음 |

- 둘 다 2단계 검증을 첫 시도에 통과했다. 생성 뒤 목표·과제가 저장되지 않았다(`/api/goals` 0건).
- 지시서가 말한 "3단계 합 25~30초"보다 성경은 37초로 길었다. 170초 예산에는 여유가 있다.
- 호출 비용: 이 확인에 실제 생성 2번(총 6회 호출) + 모델 지원 확인 2회.

## 7. 미확인 / 참고
- 2개 분야 각 1번만 실제 호출했다. 결과 품질(범위 판단, 명칭 정확성)과 더 넓은 분야 확인은 PM 확인 대상이다. 호출 시간은 입력과 모델 상태에 따라 달라진다.
- 시간 초과로 재시도하는 경로와 170초 예산 소진은 가짜 시계와 가짜 AI 로만 확인했다(실제 지연 상황은 재현하지 않음).
- 화면(브라우저)에서 줄바꿈이 보이는지는 소스 검사와 빌드까지만 확인했고 눈으로는 미확인이다(배포 후 확인 필요).
- Render 의 환경변수에 `OPENAI_PLAN_MODEL` 을 따로 설정하지 않아도 기본값 `gpt-5.4-mini` 로 동작한다. 배포 환경에서 이 모델이 계정에서 쓰일 수 있는지는 로컬 키로만 확인했다.
- 0단계 글을 2번째 단계 이후에 재사용하지 않으므로 같은 분야를 여러 번 요청하면 그만큼 호출과 시간이 든다(지시서 결정 사항).
- 작업 폴더에 이 작업과 무관한 파일이 있어 커밋하지 않았다: `docs/프롬프트와 응답사례연구.md`(사용자 파일), `frontend/AGENTS.md`, `변경관리내역서.hwp/.pdf`.
- 이번 작업 중 과거 대화에서 사용자 요청으로 만든 프롬프트 비교 시험 스크립트는 저장소 밖(임시 폴더)에 있고 저장소에는 넣지 않았다.
