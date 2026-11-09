# PaceMate 문서 지도

갱신: 2026-11-10(PM). 이 폴더의 문서는 날짜순으로 쌓여 120개가 넘는다. 대부분은 지난 작업의 지시서·보고서·검증 기록(이력)이고, **지금 기준이 되는 문서는 1~3장의 몇 개뿐**이다. 처음 보는 사람은 1장부터 읽는다. 파일은 옮기지 않고 이 지도에서 링크만 건다(옮기면 문서 사이의 경로가 깨진다).

**현재 상태를 이 문서에 복사하지 않는다.** 상태의 원본은 [change_management.md](change_management.md)다.

## 1. 기준 문서 (무엇을, 왜, 어떻게)
| 문서 | 내용 |
|---|---|
| [../README.md](../README.md) | 프로젝트 소개(문제, 기능, AI 활용, 팀, 실행 방법) |
| [../mission.md](../mission.md) | 과제 요구사항과 평가 기준 |
| [../서비스기획서.md](../서비스기획서.md) | 문제, 대상, 범위, 역할 분담 |
| [../PRD.md](../PRD.md) | 기능 요구사항과 수용 기준(FR-01~09), 비기능 |
| [../mockup/index.html](../mockup/index.html) | 표준 화면 목업(화면 변경의 기준) |
| [../TASK.md](../TASK.md) | 14일 MVP 작업 계획과 이력(**2026-11-09 종료, 동결**) |
| [../CLAUDE.md](../CLAUDE.md) | 작업 규칙(역할, 핵심 결정, 비밀값, Git) |

## 2. 지금 진행 중인 것 (여기부터 확인)
| 문서 | 내용 |
|---|---|
| [change_management.md](change_management.md) | **MVP 이후 모든 변경의 단일 기록**: CR 목록·상태(§3), 실시 내역, 배포 대기(§4), 사용자 결정 대기(§5) |
| [execution_improvement_candidates.md](execution_improvement_candidates.md) | 학습 실행 화면 개선 후보 E-1~E-7(결정 전) |
| [change_review_learning_path.md](change_review_learning_path.md) | 변경관리내역서(학습 경로 설정) No.1~8 분석 |
| [post_mvp_backlog.md](post_mvp_backlog.md) | MVP 에서 뺀 기능과 테스트 후 후보 |
| [user_test_round1.md](user_test_round1.md) | 1차 사용자 의견 메모 |

## 3. 설계 (현재 구조)
| 문서 | 내용 |
|---|---|
| [erd_current.md](erd_current.md) | 데이터 구조(ERD), 필드 이름의 기준 |
| [phase1_design.md](phase1_design.md) | API·DTO 계약 |
| [dfd_by_module.md](dfd_by_module.md) | 데이터 흐름도(레벨 0~3) |
| [phase3_auth.md](phase3_auth.md), [auth_upgrade_design.md](auth_upgrade_design.md) | 인증(익명 UID), 다른 기기에서 이어 쓰기(암호) 설계 |
| [phase4_plan.md](phase4_plan.md), [phase5f_design.md](phase5f_design.md), [multi_goal_design.md](multi_goal_design.md) | 계획 생성·주차 배치, 전체 과정 일괄 계획, 동시 학습 2개 |
| [phase5e_design.md](phase5e_design.md), [phase8b_design.md](phase8b_design.md) | 관리자(사용자·피드백), 참고자료 수집·승인 |
| [phase8c_ai_providers.md](phase8c_ai_providers.md) | AI 공급자 확장 |
| [resource_curation_roadmap.md](resource_curation_roadmap.md) | 학습 자료 큐레이션 단계 계획 |

## 4. AI 프롬프트와 개선 이력 (발표·평가용)
| 문서 | 내용 |
|---|---|
| [ai_improvement_log.md](ai_improvement_log.md) | AI 개선 이력 IMP-001~(현상, 원인, 결정, 효과) |
| [ai_prompt_inventory.md](ai_prompt_inventory.md) | AI 기능 7개와 시스템 프롬프트 목록 |
| [ai_prompts_learning_path.md](ai_prompts_learning_path.md) | 학습 경로 설정의 실제 프롬프트(호출 1~3) |
| [plan_prompt_improvement_proposal.md](plan_prompt_improvement_proposal.md), [plan_prompt_v2_draft.md](plan_prompt_v2_draft.md), [plan_prompt_test_2026-11-09.md](plan_prompt_test_2026-11-09.md) | 계획 생성 3단계 호출(CR-012)에 이른 제안·초안·비교 시험 |
| [phase6_chunk_review.md](phase6_chunk_review.md), [phase6c_resource_links.md](phase6c_resource_links.md) | RAG 자료 조각 검토, 검토된 학습 링크 |

## 5. 배포·운영
| 문서 | 내용 |
|---|---|
| [deploy_guide.md](deploy_guide.md) | 배포(Vercel, Render, Firebase 도메인) |
| [firebase_setup_guide.md](firebase_setup_guide.md) | Firebase 설정 |
| [pre_deploy_checklist.md](pre_deploy_checklist.md) | 배포 전 확인 |
| `서버실행명령` | 로컬 실행 명령 모음(모드별) |
| [project_operating_playbook.md](project_operating_playbook.md) | 협업 운영 요령(지시서·보고서·검증 템플릿) |
| [handoff_verification_prompt.md](handoff_verification_prompt.md), [handoff_dev_prompt.md](handoff_dev_prompt.md) | 새 세션 인수인계(검증팀·개발팀) |
| [team_workload.md](team_workload.md) | 영역별 업무량 비교(CR-010) |

## 6. 사용자 테스트 (2026.11.01~11.20)
| 문서 | 내용 |
|---|---|
| [tester_guide.md](tester_guide.md) | 테스터 안내문(설문 링크 포함) |
| [user_test_survey.md](user_test_survey.md), `user_test_survey_form.gs` | 설문 문항, Google 설문 생성 스크립트 |

## 7. 지난 기록 (이력, 찾아볼 때만)
작업 하나마다 **지시서 → 보고서 → 검증** 순서로 파일이 남아 있다. 이름 규칙으로 찾는다.

| 묶음 | 파일 이름 규칙 | 내용 |
|---|---|---|
| MVP Phase 2~8 | `phase{N}_dev_prompt.md` → `phase{N}_report.md` → `phase{N}_verification.md`, 수정은 `_fix_instructions`·`_fix_report`·`_fix_verification` | 14일 MVP 구현(TASK.md 의 Phase 와 같은 번호) |
| 운영 수정 | `ops_fix_instructions_*` → `ops_fix_report_*` → `ops_verification_*` | 배포 뒤 발견한 문제(한국어 출력, 모드 표시, 튜터 키 등) |
| CR(변경) | `cr{NNN}_*_dev_prompt.md` → `cr{NNN}_*report.md` → `cr{NNN}_*verification.md` | MVP 이후 변경. 번호와 상태는 change_management.md §3 |
| 기타 | `phase2_prep.md`, `plan_prd_comparison.md`, `firebase_live_check_2026-10-22.md`, `phase3_review_instructions.md`, `task_screen_check.md`(쓰지 않음) | 준비·대조·일회성 점검 |

최근에 바뀐 파일은 `ls -t docs | head` 로 찾는다.
