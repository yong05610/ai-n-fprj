# Phase 5E(관리자·피드백·동의 v1.1) 검증 결과 (PM, 2026-10-23)

**대상:** 커밋 e22b1d4, 지시서 docs/phase5e_dev_prompt.md, 개발팀 보고 docs/phase5e_report.md
**판정:** 백엔드·API·보안 규칙 승인(dev 모드). 화면 동작은 개발팀 보고만 있어 PM 미검증. Firebase 실연동, 실제 ADMIN_UIDS 로 본인 계정이 관리자 화면에 들어오는지는 미검증.

## 1. 직접 확인한 것
- backend `pytest` **406 passed**(직전 337 + 69), frontend `typecheck` 통과, `npm test` **60 passed**(직전 54 + 6), `npm run build` 통과(보고와 일치).
- 코드 읽기(`main.py`): `require_admin_uid`(인증·동의 뒤 토큰 UID 가 ADMIN_UIDS 에 있을 때만 통과, 본문·헤더·쿼리 미사용), `_admin_uids`(쉼표, 공백·빈 항목 무시, 호출마다 읽음), `_touch_last_active`(10분 이상 지났을 때만 쓰기), 피드백 문서(user_id 없음), 사용자 목록(사용자·활성 학습을 한 번씩 조회해 합산), 요약, 상태 변경(seen/candidate/done 만).
- 실제 서버(빈 포트 8215, dev + memory, `ADMIN_UIDS` 에 가짜 UID 주입, `.env` 미수정, 종료 확인):

| 확인 | 결과 |
|---|---|
| 약관 v1.0 으로 동의 시도 | 400 (현재 v1.1) |
| `is_admin` 관리자/일반 | true / false, PATCH 로 `is_admin`·`role` 을 보내도 false 유지 |
| `/api/admin/*` 3종: 일반 사용자 / 토큰 없음 / 관리자 | 403 / 401 / 200 |
| 사용자 목록 | 마스킹 ID(앞 4자 + •••)만, 응답에 전체 UID·과정명 없음, 키는 active_goal_count, consent_version, consented, last_active_at, status, user_id_masked, user_type 만 |
| 피드백 잘못된 screen / 점수 0, 6 / 의견 1001자 | 모두 422 |
| 피드백 제출, 같은 client_request_id 재전송 | 201, 200 (같은 id, 중복 없음) |
| 사용자당 한도 | 10건까지 201, 11번째부터 429 |
| 관리자 피드백 목록 | 키는 ai_usefulness, comment, created_at, id, screen, status, usability 만(UID 없음) |
| 요약 | 미확인 건수, 평균, 응답 수, 상태 변경 후 done_last_30_days 반영 |
| 상태 변경 | seen 정상, new 로 되돌리기 422, 없는 id 404, 일반 사용자 403 |
| 데이터 삭제 요청(`POST /api/user/delete-data`) 후 | 사용자 목록에서 사라지고 피드백은 그대로 남음 |
| 서버 로그에서 피드백 의견 문구 검색 | 0건 |

## 2. 미검증
- 화면(관리자 두 화면, 비관리자 메뉴 숨김, 피드백 카드, 계정 ID 복사, 동의 모달 재표시)은 개발팀 Chrome 확인 보고만 있다.
- Firebase 실연동(특히 users·goals 전체 조회, 피드백 저장), 실제 ADMIN_UIDS 로 본인 계정 진입, 모바일 폭, 목업 픽셀 비교.

## 3. 열린 결정 처리
1. 구버전 동의자 표기 "재동의 필요 (v1.0)": 승인(더 정확함). 목업은 "동의함 (v1.0)"으로 되어 있으나 구현이 맞다고 보고 목업 문구를 PM 이 고쳤다.
2. 점수 기본값 없음("선택하세요"): 승인. 기본값이 있으면 응답이 한쪽으로 치우친다. 목업도 PM 이 같게 고쳤다.
3. 피드백 카운터 경합(동시 제출 시 10건을 조금 넘을 수 있음): 승인. 배포 전 Firestore 트랜잭션 적용 여부를 확인할 항목으로 남긴다(docs/post_mvp_backlog.md).
4. 데이터 삭제 후 재동의하면 카운터 0: 설계가 허용한 사항, 승인.
5. client_request_id 전역 조회: 승인(무작위 값).
6. 사용자 목록 전체 조회 규모: 테스트 규모에서는 문제 없음. 승인.
7. 피드백 200건 초과 페이지 없음: 승인(MVP 범위).
8. **피드백 의견 보관 기한 없음: 운영 정책이라 사용자 결정이 필요하다.** 삭제 요청으로 지울 수 없는 데이터이므로, 테스트 종료 후 일괄 삭제할지 정해야 한다(docs/post_mvp_backlog.md, Phase 10 전).

## 4. 사용자가 할 일
1. 새로 받은 코드로 백엔드를 다시 시작한다(Firestore 모드). 이미 동의한 계정은 약관 v1.1 재동의 모달이 한 번 뜬다. 동의하면 기존 데이터가 그대로 보여야 한다.
2. [내 정보·설정]의 "계정 ID 복사"로 본인 UID 를 복사해 `backend/.env` 의 `ADMIN_UIDS=` 에 넣고 백엔드를 재시작한다(절차: docs/firebase_setup_guide.md §9, 값은 채팅에 쓰지 않는다).
3. 새로고침 후 사이드바에 관리자 그룹이 보이는지, 사용자 관리·사용자 피드백 화면이 열리는지 확인한다.
4. 설정에서 테스트 피드백을 한 번 제출하고 관리자 피드백 화면에 나타나는지, 상태를 바꿨을 때 요약이 변하는지 확인한다.
5. 일반 사용자 계정(다른 브라우저나 시크릿 창)으로 들어갔을 때 관리자 메뉴가 없는지 확인한다.
