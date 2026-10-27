# 영역별 업무량 비교표 (CR-010)

작성: 검증/PM, 2026-10-27. 서비스기획서 9.1(영역별 역할과 담당)의 근거 자료다. 이전에는 변경관리 문서 §3-1 에 측정 결과 한 줄만 있었고 측정 방법이 남아 있지 않아, **다시 잴 수 있는 방법으로 처음부터 측정**했다. 그래서 이전 숫자(DB 약 1,460, AI 약 1,360 등)와 직접 비교하지 않는다.

## 1. 결과 (빈 줄을 뺀 줄 수, 2026-10-27, 커밋 c44837f 기준)
### 1-1. 영역별
| 영역 | 담당(구현 / 검증) | 코드 | 테스트 |
|---|---|---:|---:|
| ① 프론트엔드(사용자 UI) | member1 / member2 | 5,494 | 939 |
| ② 백엔드(DB 인터페이스) | member2 / member1 | 1,784 | 2,080 |
| ② 공유 DTO(`schemas.py`, 계약 관리는 ② 담당) | member2 / member1 | 744 | - |
| ③ 백엔드(AI 인터페이스) | member3 / member4 | 1,551 | 2,897 |
| ④ 관리자: 참고자료 수집·관리 | member4 / member3 | 2,173 | 2,128 |
| ④ 관리자: 사용자 관리·피드백 | member4 / member3 | 490 | 414 |
| 합계 | | 12,236 | 8,458 |

### 1-2. 튜터 대화 관리 이동의 영향 (2026-10-27, DFD P2.16·P2.17 → P3.6·P3.7)
| 영역 | 이동 전 코드 | 이동 후 코드 | 차이 |
|---|---:|---:|---:|
| ② DB 인터페이스 | 1,922 | 1,784 | -138 |
| ③ AI 인터페이스 | 1,413 | 1,551 | +138 |

옮겨 간 것: API 함수 4개(`list_conversations`, `create_conversation`, `get_conversation`, `get_data_summary`)와 이들만 쓰는 보조 함수(`_conversation_out`, `_decorated_messages`, `_current_learning`, `_learning_context`). 테스트는 이미 튜터 테스트 파일(`test_phase6_tutor.py`, ③)에 있어 변화가 없다.

### 1-3. 팀원별 (구현 + 검증)
| 팀원 | 구현 코드 | 검증 코드 | 합계 | 구현 테스트 |
|---|---:|---:|---:|---:|
| member1 | 5,494 (①) | 2,528 (②+DTO) | 8,022 | 939 |
| member2 | 2,528 (②+DTO) | 5,494 (①) | 8,022 | 2,080 |
| member3 | 1,551 (③) | 2,663 (④) | 4,214 | 2,897 |
| member4 | 2,663 (④) | 1,551 (③) | 4,214 | 2,542 |

## 2. 읽는 법 (PM 의견)
- **줄 수는 노력과 같지 않다.** ③ AI 는 줄 수는 적지만 프롬프트 반복 수정, 실제 모델 호출 확인(비용), 규칙 위반 재시도 설계가 들어가 줄당 노력이 크다(개선 이력 IMP-004·IMP-008 참고). ④ 참고자료는 외부 주소를 읽는 보안(SSRF·프롬프트 주입) 시험이 크다. ① 프론트는 줄 수가 많지만 화면 코드의 비중이 크다.
- 교차 검증이 짝(1↔2, 3↔4)이라 **짝 안에서는 구현+검증 합이 같지만, 짝 사이에는 줄 수로 약 2배 차이**가 난다(member1·2: 8,022, member3·4: 4,214). 테스트 줄 수는 반대로 member3·4 쪽이 많다(③ 2,897, ④ 2,542).
- 서비스기획서 9.2 는 "업무량 차이는 검증 배정으로 조정"한다고 정했다. 조정이 필요한지, 필요하면 어떻게 할지(예: 공통 업무인 README·발표·테스터 운영을 member3·4 에 더 배정, ① 검증 일부를 member3·4 와 나눔)는 **사용자 결정**이다.

## 3. 측정 방법 (다시 잴 때 이대로)
1. 대상: `git ls-files backend frontend` 중 `.py`, `.ts`, `.tsx`, `.css`. 빈 줄만 뺀다(주석은 포함).
2. 테스트: `backend/tests/*`, `frontend/**/*.test.ts`. 나머지는 코드.
3. `backend/main.py`(모든 API 가 들어 있는 파일)는 **함수 단위**로 나눈다.
   - API 함수는 DFD(`docs/dfd_by_module.md` 4-6 표)의 영역을 따른다: `/api/admin/resources*` → ④ 참고자료, 그 밖의 `/api/admin*` → ④ 사용자·피드백, `/api/path/ideas`·`/api/path/recommend`·`/api/plan/generate`·`/api/data/summary`·`/api/conversations*`·`POST /api/goals/{id}/insight` → ③, 나머지(`/health` 포함) → ②.
   - 보조 함수는 그 함수를 (직접·간접으로) 부르는 API 의 영역이 하나면 그 영역, 여럿이면 ②(공통).
   - 함수 밖의 코드(import, 앱 설정, 상수) → ②.
4. 백엔드 모듈 파일:
   - ③: `ai_client.py`(AI 공통 부품, ③ 소유·③④ 공용), `rag.py`, `tutor.py`, `insight_rules.py`, `schedule.py`, `resources_catalog.py`, `prompts.py` 150행까지, `ai_schemas.py` 84행까지.
   - ④ 참고자료: `resource_*.py`, `link_checker.py`, `page_metadata.py`, `field_demand.py`, `prompts.py` 151행부터, `ai_schemas.py` 85행부터(수집용 AI 프롬프트·스키마).
   - 공유 DTO: `schemas.py`.
   - ②: 나머지(`auth.py`, `store.py`, `clock.py`, `errors.py`, `deploy_config.py`).
5. 백엔드 테스트 파일: 이름에 `phase8b` → ④ 참고자료, `phase5e_admin` → ④ 사용자·피드백, `ai_client`·`korean`·`phase4_plan`·`phase5f`·`phase6*`·`resources_catalog`·`test_schedule` → ③, 나머지 → ②. 파일 안에서 더 나누지 않는다(예: `test_phase4_plan.py` 의 계획 확정 시험도 ③ 으로 센다).
6. 프론트: `AdminLibrary*`, `ResourceCandidate*`, `adminResources*`, `resourceCandidateCard*` → ④ 참고자료, `AdminUsers*`, `AdminFeedback*`, `adminLabels*` → ④ 사용자·피드백, 나머지(`globals.css`, `page.tsx` 포함) → ①.

**한계:** `schedule.py`, `resources_catalog.py` 는 ②(계획 확정, 참고자료 보기)도 쓰지만 ③에 넣었다. 테스트는 파일 단위라 섞인 파일이 있다. 측정 스크립트는 PM 의 임시 폴더에서 실행했으며 저장소에는 두지 않았다(이 절차로 다시 만들 수 있다).
