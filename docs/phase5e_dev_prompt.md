# Phase 5E 개발 지시서 — 관리자(사용자 관리·피드백)와 동의 v1.1

작성: 검증/PM, 2026-10-23. 끝나면 docs/phase5e_report.md 로 보고하고 멈춘다. 6B(인사이트), 7 은 시작하지 않는다(뼈대도 만들지 않는다). **선행:** Phase 5D 백엔드 승인(docs/phase5d_verification.md).

## 0. 목적과 범위
사용자 테스트(Phase 8) 운영을 위해 (1) 관리자 식별, (2) 사용자 관리 화면, (3) 앱 안 피드백 수집, (4) 피드백 관리 화면, (5) 동의 문구 변경과 약관 v1.1 을 만든다. 설계 기준은 **docs/phase5e_design.md**(사용자 승인 2026-10-22), PRD FR-07, docs/erd_current.md 이다. 이 지시서는 그 설계를 구현 단위로 나눈 것이며 충돌하면 설계 문서를 따르고 보고서에 알린다.

**만들지 않는 것:** 운영 현황, AI 생성 이력, 참고자료 관리, 서비스 설정 화면(사이드바에서 계속 "준비 중" 비활성), 이메일 사용자 유형, 관리자의 사용자 데이터 수정·삭제, 피드백 의견 수정·삭제, 피드백 페이지 처리(200건 초과), 외부 설문 연동.

## 1. 기준
- 화면은 mockup/index.html 의 `page-admin-users`, `page-admin-feedback`, `page-settings`(피드백 카드), 동의 모달 문구와 **나란히 비교해 맞춘다**. 앱 셸과 스타일은 5C 에서 맞춰져 있으니 기존 클래스를 재사용한다. 목업 전용(.impl-badge, "관리자 목업" 배지, 예시 데이터, `admin-banner` 의 "예시 데이터입니다" 문구)은 가져오지 않는다. 보고서에 화면 대조표를 넣는다(규칙: docs/phase5c_dev_prompt.md §1). 목업은 PM 이 이번에 사용자 관리 표, 설정의 피드백 카드, 동의 문구를 설계에 맞게 고쳤다.
- 핵심 결정은 CLAUDE.md 를 따른다(UID 는 토큰에서만, ErrorResponse, 쓰기 멱등, 로그에 사용자 입력 원문 금지, 날짜는 backend/clock.py 와 frontend/lib/week.ts 만).

## 2. 관리자 식별 (E.1)
- 환경변수 `ADMIN_UIDS`(쉼표 구분, 공백 제거, 빈 값이면 관리자 없음). 코드, 테스트, 문서에 실제 UID 를 쓰지 않는다(테스트는 가짜 dev UID 를 환경변수로 주입).
- 의존성 `require_admin_uid`: 먼저 `require_consented_uid` 와 같은 인증·동의 검사를 거친 뒤 UID 가 목록에 있을 때만 통과, 아니면 403 ErrorResponse. 토큰 없음 401. **요청 본문, 헤더, 쿼리의 어떤 값도 관리자 판단에 쓰지 않는다.**
- `GET /api/user/profile`(UserProfileResponse)에 `is_admin: bool` 추가(읽기 전용). `PATCH /api/user/profile` 에 `is_admin`, `role` 을 실어 보내도 무시되거나 422 이며 어떤 경우에도 바뀌지 않는다(테스트).
- 프론트: `is_admin` 이 true 일 때만 사이드바 관리자 그룹을 보인다. 비관리자에게는 그룹 전체를 숨긴다. 관리자에게 그룹 제목은 "관리자"(더 이상 "준비 중" 아님), 항목 중 "사용자 관리", "사용자 피드백"은 활성, 나머지 4개(운영 현황, AI 생성 이력, 참고자료 관리, 서비스 설정)는 기존처럼 비활성 + "준비 중".
- [내 정보·설정]에 작은 영역 "관리자 등록용 계정 ID"와 **"계정 ID 복사" 버튼**을 둔다(모든 사용자가 자기 UID 만 본다. 클립보드 복사 후 "복사했어요" 표시, 복사 실패 시 선택 가능한 텍스트로 보여 준다). 운영 안내는 docs/firebase_setup_guide.md §9 에 PM 이 작성해 두었다.

## 3. 사용자 관리 (E.2)
- `GET /api/admin/users?status=all|active|dormant&page=1`(관리자 전용, 기본 all, 페이지당 50건, 최근 활동 내림차순). 응답 항목: `user_id_masked`(UID 앞 4자 + "•••", 4자 이하이면 전체를 가리지 않고 앞 1자 + "•••"), `user_type`("익명" 고정), `consented`(bool), `consent_version`, `active_goal_count`(status=active 인 학습 수), `last_active_at`, `status`("active"|"dormant"). 응답 최상위에 `total`, `page`, `page_size`.
- **전체 UID, 과정명, 목표 내용, 회고, 대화, 토큰은 응답에 절대 포함하지 않는다**(테스트로 응답 문자열 검사).
- 활성 = `last_active_at` 이 오늘(Asia/Seoul, `clock.py`)로부터 7일 이내. 아니면 휴면. 필터는 이 정의로 거른다.
- 사용자와 학습 수는 한 번의 조회로 모으고(사용자 수만큼 반복 조회 금지) 서버에서 합산한다.
- **`last_active_at` 갱신:** 지금은 동의와 프로필 수정 때만 갱신돼 "최근 활동"이 부정확하다. 인증·동의된 요청 처리에서 갱신하되 쓰기가 폭주하지 않게 **마지막 갱신으로부터 10분이 지났을 때만** 쓴다(읽기 요청도 포함, 하지만 `GET /api/admin/*` 은 제외하지 않아도 된다). 구현 위치와 방식은 개발팀이 정하고 보고서에 적는다. 기존 테스트가 통과해야 한다.
- 화면: 목업 page-admin-users. 열 = 사용자 ID, 유형, 동의("동의함 (v1.1)" / "동의 안 함"), 진행 중 학습("N개"), 최근 활동, 상태 pill. 우측 상단 상태 필터(전체/활성/휴면). 읽기 전용이다. 로딩, 빈 목록, 오류, 재시도 상태를 둔다. 최근 활동은 서비스 시간대 표기(`week.ts` 의 함수 재사용). 페이지가 2개 이상이면 이전/다음 버튼.

## 4. 피드백 수집 (E.3)
- `POST /api/feedback`(require_consented_uid): 요청 `{usability: 1~5, ai_usefulness: 1~5, screen: dashboard|path|execution|analysis|settings|other, comment?: 1000자 이하, client_request_id}`.
- **저장 문서(feedback 컬렉션)에는 user_id, UID, 토큰, 연락처, IP 를 저장하지 않는다.** 필드: usability, ai_usefulness, screen, comment(없으면 빈 문자열), status("new"), client_request_id, created_at, updated_at. 서버는 UID 로 인증만 한다.
- 멱등: 같은 `client_request_id` 로 다시 보내면 중복 저장 없이 기존 결과를 200 으로 돌려준다(조회 키는 client_request_id 만 쓴다. UID 로 찾지 않는다).
- 남용 방지: users 문서의 `feedback_submitted_count` 가 이미 10 이면 429(ErrorResponse, 메시지는 내용과 무관). 멱등 재요청은 카운트를 올리지 않는다. 카운터는 users 문서에만 있고 피드백 문서와 연결되지 않는다.
- 의견 원문을 로그와 오류 메시지에 남기지 않는다(`caplog` 테스트).
- **`DELETE /api/user/data`(데이터 삭제) 뒤에도 피드백은 남는다.** `USER_OWNED_COLLECTIONS` 에 feedback 을 넣지 않는다(테스트: 삭제 후 피드백 문서가 남고 users 문서는 사라짐).
- 화면: [내 정보·설정]의 "테스트 피드백" 카드(목업 settings). 필드는 목업과 같고, 입력 칸 아래에 "피드백에는 사용자 정보가 저장되지 않아 제출 후 삭제 요청으로 지울 수 없어요." 표시. 제출 중 버튼 비활성, 성공 시 "보내 주셔서 고마워요" 표시와 입력 초기화, 실패 시 입력을 보존하고 같은 `client_request_id` 로 재시도(재시도해도 중복 저장되지 않음). 429 면 "이번 테스트에서 보낼 수 있는 피드백 수를 넘었어요." 안내. 기존 설정 화면의 "테스트 피드백 안내" 버튼이 있다면 이 카드로 대체한다.

## 5. 피드백 관리 (E.4)
- `GET /api/admin/feedback?status=all|new|seen|candidate|done&limit=100`(관리자 전용, 최신순, limit 최대 200): 항목 `{id, created_at, screen, usability, ai_usefulness, comment, status}`. **user_id 등 식별 필드는 문서에 없으므로 내려갈 것도 없다.**
- `GET /api/admin/feedback/summary`: `{unseen_count(status=new), usability_avg, usability_count, ai_usefulness_avg, ai_usefulness_count, candidate_count, done_last_30_days}`. 평균은 소수점 한 자리, 응답이 없으면 null. `done_last_30_days` = status=done 이고 updated_at 이 최근 30일(Asia/Seoul)인 건수.
- `PATCH /api/admin/feedback/{id}` `{status: seen|candidate|done}` 로 상태만 바꾼다(new 로 되돌리는 값은 422). 의견 수정·삭제 API 는 만들지 않는다.
- 화면: 목업 page-admin-feedback. 우측 상단 pill "미확인 N건", 통계 카드 4개(사용성 평균·응답 수, AI 답변 유용성 평균·응답 수, 개선 후보, 반영 완료 최근 30일), 목록 행(날짜, 의견 인용, "{화면 이름} · 익명 테스터 · 유용성 n/5"(여기서 n 은 ai_usefulness), 상태 변경 버튼). 상태 버튼은 눌렀을 때 선택지(확인, 개선 후보, 반영 완료)를 고르거나 순환 방식 중 하나를 택해 목업과 같은 모양으로 맞추고 선택한 방식을 보고서에 적는다. 의견이 없으면 "(의견 없음)". 빈 상태, 로딩, 오류, 재시도. 의견은 React 이스케이프로만 표시한다.

## 6. 동의 문구와 약관 v1.1 (E.5)
- `CURRENT_TERMS_VERSION = "v1.1"`(backend/main.py), 프론트 `TERMS_VERSION`(frontend/lib/consent.ts)도 "v1.1".
- 동의 모달의 "데이터 삭제" 항목 아래에 한 줄 추가: **"테스트 피드백을 제출하면 사용자 정보 없이 저장되어, 이후 삭제 요청으로 지울 수 없습니다. 피드백 제출은 선택입니다."**(목업 문구와 같게)
- v1.0 으로 동의한 기존 사용자는 모든 개인 데이터 API 에서 CONSENT_REQUIRED 를 받고, 프론트가 동의 모달을 다시 보여 재동의하면 `consent_version` 이 v1.1 로 갱신되어 이전 데이터가 그대로 보이는지 확인한다(테스트: v1.0 사용자 문서를 만들고 재동의 흐름). 재동의 때 `last_active_at` 도 갱신된다.
- 기존 테스트가 쓰는 "v1.0" 상수는 v1.1 로 맞춘다(바꾼 파일 목록을 보고서에 적는다).

## 7. 계약 문서 갱신 (함께)
`backend/schemas.py`, `docs/erd_current.md`(feedback 컬렉션, users 의 feedback_submitted_count, 약관 v1.1), `docs/phase1_design.md`(API 표: /api/admin/users, /api/admin/feedback, /api/admin/feedback/summary, /api/admin/feedback/{id}, /api/feedback, profile.is_admin), 프론트 타입. 해당 항목만 고치고 보고서에 알린다. `docs/firebase_setup_guide.md` §9 는 PM 이 이미 썼다.

## 8. 보안·검증 기준 (테스트 포함)
- 비관리자가 `/api/admin/*` 호출 → 403, 토큰 없음 → 401, 동의 전 → 403 CONSENT_REQUIRED.
- 요청에 `is_admin`, `role` 을 실어도 관리자가 되지 않는다.
- ADMIN_UIDS 가 비어 있으면 아무도 관리자가 아니다. 쉼표·공백 처리.
- 피드백 문서에 UID 관련 필드가 없다(저장 문서 검사). 피드백 멱등. 10건 한도 429. 삭제 후 피드백 잔존.
- 관리자 사용자 목록 응답에 전체 UID, 과정명, 회고, 대화가 없다. 필터, 페이지, 휴면 경계(7일, Asia/Seoul).
- 피드백 요약 평균, 응답 수 0 일 때 null, 상태 변경, 잘못된 상태 422, 없는 id 404.
- 약관 v1.0 → v1.1 재동의 흐름.
- 현재 pytest 337건, 프론트 테스트 54건이 모두 통과해야 한다(일부 기대값만 v1.1 로 바뀐다).
- 실제 서버(빈 포트, AUTH_MODE=dev STORE_BACKEND=memory 환경변수 덮어쓰기, `.env` 수정 금지, 끝나면 종료)에서 관리자 UID 를 `ADMIN_UIDS` 환경변수로 주입해 관리자 두 화면, 비관리자 숨김, 피드백 제출 → 관리 화면 반영 → 상태 변경, 설정의 UID 복사까지 브라우저로 확인하고 확인하지 못한 것은 "미검증"으로 적는다.

## 9. 보고서(docs/phase5e_report.md)
변경 요약, 테스트 건수(실제), 화면 대조표(목업 page-admin-users, page-admin-feedback, page-settings 와 나란히), API/DTO 변경 표, `last_active_at` 갱신 방식, 바꾼 기존 테스트 목록, 상태 버튼 방식, 미검증, 열린 결정. 채팅에는 한 줄 요약만 남긴다. 커밋 전 pytest, typecheck, test, build 통과를 확인하고 비밀값, `frontend/AGENTS.md`, `next-env.d.ts` 는 포함하지 않는다. `backend/.env` 의 `ADMIN_UIDS` 는 사용자가 직접 넣으므로 개발팀은 값을 만들거나 쓰지 않는다.
