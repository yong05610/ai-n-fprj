# Phase 5E 보고 — 관리자(사용자 관리·피드백)와 동의 v1.1

**기준:** docs/phase5e_dev_prompt.md, docs/phase5e_design.md, PRD FR-07, mockup `page-admin-users`, `page-admin-feedback`, `page-settings`
**상태:** 2026-10-23 구현 완료, 재검증 대기. 6B(인사이트), 7 은 시작하지 않았다.
**환경:** `backend/.env` 가 firebase 모드라서 확인용 서버는 `AUTH_MODE=dev STORE_BACKEND=memory ADMIN_UIDS=qa-admin-uid`(백엔드, 빈 포트 8123), `NEXT_PUBLIC_AUTH_MODE=dev NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8123`(프론트, 빈 포트 3123)을 명령줄 환경변수로 덮어써서 띄우고 확인 후 종료했다. `ADMIN_UIDS` 에는 확인용 가짜 UID 만 넣었고 `.env`, `.env.local` 은 수정하지 않았다. 이미 떠 있는 서버는 건드리지 않았다. 이번 Phase 에서 OpenAI 는 호출하지 않았다. 코드, 테스트, 문서에 실제 UID 는 없다.

## 1. 변경 요약

- **관리자 식별(E.1):** 환경변수 `ADMIN_UIDS`(쉼표 구분, 공백 제거, 빈 값이면 관리자 없음)를 요청마다 읽는 `require_admin_uid` 의존성. `require_consented_uid`(인증·동의)를 먼저 거친 뒤 토큰의 UID 만으로 판단하며 본문·헤더·쿼리는 쓰지 않는다. `GET /api/user/profile` 에 읽기 전용 `is_admin`.
- **사용자 관리(E.2):** `GET /api/admin/users`(마스킹 ID, 동의, 진행 중 학습 수, 최근 활동, 활성/휴면, 50건 페이지, 상태 필터) + 화면.
- **피드백 수집(E.3):** `POST /api/feedback`(사용자 정보 없이 저장, 멱등, 사용자당 10건 한도) + [내 정보·설정]의 "테스트 피드백" 카드. 설정에 "관리자 등록용 계정 ID 복사" 카드.
- **피드백 관리(E.4):** `GET /api/admin/feedback`, `GET /api/admin/feedback/summary`, `PATCH /api/admin/feedback/{id}`(상태만) + 화면.
- **동의 v1.1(E.5):** `CURRENT_TERMS_VERSION`·`TERMS_VERSION` 을 "v1.1" 로, 동의 모달에 피드백 저장 안내 한 줄. v1.0 동의자는 재동의 흐름으로 이어진다.
- 사이드바: 관리자에게만 그룹 "관리자"가 보이고(비관리자에게는 그룹 전체가 없음), 사용자 관리·사용자 피드백만 활성, 나머지 4개는 "준비 중" 비활성.

## 2. 테스트 결과

- backend `pytest`: **406 passed** (직전 337 + 신규 69: `tests/test_phase5e_admin.py`). 기존 테스트는 아래 §6 의 기대값만 바꾸고 모두 통과.
- frontend: `npm run typecheck` 통과, `npm test` **60건 통과**(직전 54 + 신규 6: `lib/adminLabels.test.ts`), `npm run build` 통과.
- 실제 서버 + 실제 Chrome 으로 지시서 §8 시나리오를 확인했다(§7).

## 3. API / DTO 변경 표

| 대상 | 변경 | 비고 |
|---|---|---|
| `UserProfileResponse` | `is_admin: bool` 추가 | 파생 값(ADMIN_UIDS 에서 계산), 저장·수정 불가. `PATCH /api/user/profile` 에 `is_admin`, `role` 을 실어도 모델이 무시한다(`ProfileUpdateRequest` 는 `active_goal_id` 만 받음). 테스트로 확인 |
| `POST /api/feedback` | 신규 | 요청 `{usability 1~5, ai_usefulness 1~5, screen, comment? ≤1000자, client_request_id}`, 응답 `{id, created_at}`(첫 저장 201, 같은 키 재요청 200). 사용자당 10건 초과 429 `FEEDBACK_LIMIT_REACHED` |
| `GET /api/admin/users` | 신규(관리자) | `?status=all\|active\|dormant&page=`, 응답 `{items[], total, page, page_size}`. 항목 = `user_id_masked`, `user_type`(익명), `consented`, `consent_version`, `active_goal_count`, `last_active_at`, `status` |
| `GET /api/admin/feedback` | 신규(관리자) | `?status=all\|new\|seen\|candidate\|done&limit=`(기본 100, 최대 200), 최신순. 항목 = `id, created_at, screen, usability, ai_usefulness, comment, status` |
| `GET /api/admin/feedback/summary` | 신규(관리자) | `unseen_count, usability_avg/count, ai_usefulness_avg/count, candidate_count, done_last_30_days` (평균은 소수 한 자리, 응답 없으면 null) |
| `PATCH /api/admin/feedback/{id}` | 신규(관리자) | `{status: seen\|candidate\|done}` 만. `new`·알 수 없는 값 422, 없는 id 404. 의견 수정·삭제 API 는 없다(DELETE 는 405) |
| `feedback` 컬렉션 | 신규 | 필드 = `id, usability, ai_usefulness, screen, comment, status, client_request_id, created_at, updated_at`. **user_id·UID·토큰·연락처·IP 필드 없음**(저장 문서 전체 검사 테스트). `USER_OWNED_COLLECTIONS` 에 넣지 않음 |
| `users` | `feedback_submitted_count`(선택) | 한도용 카운터. 피드백 문서와 연결되지 않음 |
| 약관 | `CURRENT_TERMS_VERSION = "v1.1"` | `TERMS_VERSION_MISMATCH` 응답의 `current_version` 도 v1.1 |

계약 문서 갱신: `backend/schemas.py`, `docs/erd_current.md`(feedback, users 필드, 약관 v1.1), `docs/phase1_design.md`(API 표 6행과 profile.is_admin), 프론트 타입. 지시서가 말한 `DELETE /api/user/data` 는 실제 코드의 기존 `POST /api/user/delete-data` 를 가리키는 것으로 읽었다(엔드포인트를 새로 만들지 않았다).

## 4. `last_active_at` 갱신 방식 (지시서 §3 요구)

- **위치:** `require_consented_uid` 와 `require_consented_user_doc` 의 동의 검사 직후 `_touch_last_active(db, user)`. 동의된 요청(읽기 포함)에만 적용되며 동의 전·구버전 동의 요청은 쓰지 않는다. 이미 읽어 둔 users 문서(`get_current_user_doc`)의 값을 쓰므로 추가 읽기가 없다.
- **규칙:** 저장된 값이 10분 이상 지났거나 없을 때(또는 읽을 수 없는 값일 때)만 현재 시각으로 한 번 쓴다. 10분 안의 요청은 쓰기 0건(테스트로 확인). 기존의 동의·프로필 수정 갱신은 그대로.
- **구현 선택:** 현재 시각은 `_now_iso()` 가 아니라 `datetime.now(timezone.utc)` 로 계산한다. 기존 테스트가 `_now_iso` 를 호출 순서에 의존해 흉내 내고 있어(타이머 테스트) 그 호출 수를 바꾸지 않기 위해서다.
- 비용: 사용자당 최대 10분에 한 번 쓰기 한 건 추가(Firestore 에서도 미미).

## 5. 상태 버튼 방식 (지시서 §5 요구)

목록 행 오른쪽에 **현재 상태 이름의 보조 버튼**(목업과 같은 모양: "미확인", "확인", "개선 후보", "반영 완료")을 두고, 누르면 행 안에 **선택지 세 개(확인 / 개선 후보 / 반영 완료)가 칩으로 펼쳐진다**. 선택하면 즉시 저장하고 행과 요약(미확인 건수, 개선 후보, 반영 완료)을 갱신한다. 순환 방식이 아니라 선택 방식이며 "미확인"으로 되돌리는 선택지는 없다(서버도 422).

## 6. 바꾼 기존 테스트 목록

- `tests/conftest.py`, `tests/test_phase4_plan.py`, `tests/test_phase5_exec.py`, `tests/test_phase5b_multi.py`: 동의 요청의 `"v1.0"` → `"v1.1"`.
- `tests/test_phase3_auth.py`: 위와 같고, 추가로 `test_consent_creates_new_record_when_terms_version_changes` 는 "버전이 바뀌면 새 동의 기록이 생긴다"를 확인하는 테스트라 `v1.1` 로 올리는 대신 **`v1.2`** 로 바꿔 같은 의미를 유지했다.
- 프론트 테스트는 바뀐 것이 없다.

## 7. 화면 대조표

### page-admin-users
| 요소 | 결과 |
|---|---|
| 헤딩(ADMIN · USERS, "사용자 관리", 설명), 우측 상태 필터(전체/활성/휴면) | 같음 |
| 읽기 전용 안내(admin-banner) | 같음. "아래는 예시 데이터입니다" 부분은 가져오지 않음(지시) |
| 표 열: 사용자 ID, 유형, 동의, 진행 중 학습, 최근 활동, 상태 | 같음. "삭제 요청" 열 없음(설계) |
| 사용자 ID | 목업 "user_•••21"(예시)과 **다름**: 지시에 따라 UID 앞 4자 + "•••"(예: `qa-a•••`) |
| 동의 | "동의함 (v1.1)". 구버전 동의자는 "재동의 필요 (v1.0)", 동의 기록 없음은 "동의 안 함"(구현에만 있는 구분) |
| 최근 활동 | 목업 "오늘 10:42 / 어제 17:10 / 10월 14일"과 **다름**: `week.ts` 의 `dateTimeKSTLabel` 재사용으로 "10/23 15:23" |
| 상태 pill | 같음(활성 초록, 휴면 회색) |
| 페이지 이전/다음, 로딩, 빈 목록("조건에 맞는 사용자가 없어요."), 오류 + 다시 시도 | 구현에만 있음(의도적, 지시) |

### page-admin-feedback
| 요소 | 결과 |
|---|---|
| 헤딩(ADMIN · USER VOICE, "사용자 피드백", 설명), 우측 pill "미확인 N건" | 같음 |
| 통계 카드 4개(사용성 평균 n / 5 응답 N명, AI 답변 유용성, 개선 후보 "우선순위 검토", 반영 완료 "최근 30일") | 같음. 응답이 없으면 평균은 "–" |
| 목록 행(날짜 MM/DD, “의견”, "{화면} · 익명 테스터 · 유용성 n/5", 상태 버튼) | 같음. 의견이 없으면 "(의견 없음)", 의견은 React 이스케이프로만 표시(`<b>` 를 넣어도 글자로 보임, 브라우저 확인) |
| 상태 버튼의 동작 | 목업은 모양만 있음. 구현은 §5 의 선택 방식 |
| 빈 상태("아직 받은 피드백이 없어요."), 로딩, 오류 + 다시 시도, 상태 변경 실패 안내 | 구현에만 있음 |

### page-settings (피드백 카드와 계정 ID)
| 요소 | 결과 |
|---|---|
| "테스트 피드백" 카드: 제목, 안내 한 줄, 필드 4개, 입력 칸 아래 안내, "피드백 보내기" | 같음. 화면 선택지는 목업과 같음(대시보드, 학습 경로 설정, 학습 실행 기록, 종합 학습 분석, 내 정보·설정, 기타) |
| 점수 선택(1~5) | **다름**: 목업은 5 가 기본으로 선택되어 있지만 구현은 "선택하세요"로 시작하고 두 점수를 고르기 전에는 보내기 버튼이 비활성(기본값 5 가 통계를 부풀리지 않게) |
| 제출 중/성공/실패/한도 | 구현에만 있음: 제출 중 "보내는 중…", 성공 "보내 주셔서 고마워요"와 입력 초기화, 실패 시 입력 유지 + 같은 `client_request_id` 로 재시도, 429 "이번 테스트에서 보낼 수 있는 피드백 수를 넘었어요." |
| 목업 "테스트 피드백 안내" 버튼 | 가져오지 않음(5C 에서도 없었음) |
| "관리자 등록용 계정 ID" 카드(계정 ID 복사 버튼, "복사했어요", 복사 실패 시 선택 가능한 입력칸) | 목업에 없음, 지시 요구 |
| 학습 프로필 카드 | 만들지 않음(Phase 7.3) |

### 동의 모달
| 요소 | 결과 |
|---|---|
| "데이터 삭제" 항목 아래의 피드백 안내 한 줄 | 같음: "테스트 피드백을 제출하면 사용자 정보 없이 저장되어, 이후 삭제 요청으로 지울 수 없습니다. 피드백 제출은 선택입니다." |
| 모달 전체 문구 구조(수집하는 정보 / AI 활용 / 데이터 삭제 목록, 안내 버전 표시) | 5C 보고서의 차이 목록 그대로. 이번에 안내 버전 표시가 "v1.1"로 바뀜 |

## 8. 실제 서버 + 브라우저 확인 (Chrome 자동 스크립트, 전부 통과)

- **비관리자(학습자):** 사이드바에 관리자 그룹이 없음(텍스트 "관리자" 자체가 없음), `#admin-users` 로 들어가도 대시보드로 되돌아감, API 직접 호출은 403. [내 정보·설정]에 계정 ID 카드와 피드백 카드, 삭제 영역은 그대로.
- **계정 ID 복사:** 클립보드에 본인 UID 가 들어가고 "복사했어요" 표시. 복사가 거부되면 선택 가능한 읽기 전용 입력칸에 ID 표시.
- **피드백:** 점수 선택 전 버튼 비활성, 입력 칸 아래 안내 문구, 503 으로 첫 시도 실패 → 입력 유지·"다시 시도" → **같은 `client_request_id`** 로 재전송되어 성공(중복 저장 없음), 입력 초기화, 한도(429) 응답이면 한도 안내.
- **관리자:** 그룹 제목 "관리자", 활성 2개와 비활성 4개("준비 중"). 사용자 관리: 마스킹 ID 만, 전체 UID·과정명 없음, 동의/학습 수/상태, 필터(휴면은 빈 목록 안내, 활성은 3명). 사용자 피드백: "미확인 3건", 평균(사용성 3.7, 유용성 3.0)과 응답 수, 행 표기, 식별 정보 없음. 상태 버튼 → 세 선택지(미확인 없음) → "개선 후보" 선택 → 행과 요약(미확인 2건, 개선 후보 1) 즉시 갱신 → 새로고침 후에도 화면과 상태 유지.
- **재동의:** 브라우저에 v1.0 동의만 남은 계정으로 접속하면 동의 모달이 다시 뜨고 새 문구와 v1.1 이 보이며, 동의하면 대시보드로 가고 이전 데이터(과정)가 그대로 보임. (서버의 v1.0 문서 → CONSENT_REQUIRED → 재동의 → v1.1 갱신은 pytest 로 확인.)
- 서버 로그 검색: 의견 원문, UID, 과정명 0건. 페이지 오류 없음.

## 9. 미검증

- Firebase 실연동(Firestore 에서 `users` 전체 조회, `feedback` 컬렉션 쓰기와 서버 전용 접근). 보안 규칙(`firebase/firestore.rules`)은 바꾸지 않았다: `feedback` 은 클라이언트가 읽을 수 있는 컬렉션 목록에 없어 기본 거부이고, 모든 접근은 서버(Admin SDK)를 거친다.
- 실제 `ADMIN_UIDS`(사용자가 `backend/.env` 에 직접 넣음)로 본인 계정이 관리자 화면에 들어오는지. 실제 UID 확인은 사용자가 계정 ID 복사 버튼으로 한다.
- 모바일·태블릿 폭의 관리자 화면 배치. 표가 좁은 폭에서는 가로 스크롤(`table-wrap`)이 되도록 했지만 화면으로는 확인하지 않았다.
- 목업과 픽셀 단위 비교는 하지 않았다(구조·문구 대조).

## 10. 열린 결정

1. **관리자 목록의 구버전 동의자 표기**("재동의 필요 (v1.0)")를 둘지. 지시서는 "동의함 / 동의 안 함" 두 상태만 말한다.
2. **점수 기본값 없음**(§7)이 의도에 맞는지.
3. **피드백 카운터의 경합.** 한도 검사와 증가가 읽고 쓰는 방식이라 같은 사용자가 거의 동시에 여러 건을 보내면 10건을 조금 넘을 수 있다. Firestore 전환 뒤 트랜잭션으로 바꿔야 한다(타이머 시작과 같은 한계).
4. **한도 우회:** 데이터 삭제 요청 후 다시 동의하면 users 문서가 새로 생겨 카운터가 0 이 된다(설계 문서가 허용한 사항). 남용이 문제가 되면 별도 방법이 필요하다.
5. **`client_request_id` 조회는 전역**이다(사용자와 무관한 값으로만 찾으라는 지시). 서로 다른 사용자가 같은 키를 쓰는 일은 무작위 값이라 사실상 없지만, 만에 하나 충돌하면 먼저 만든 피드백의 id 만 돌려준다(내용 노출 없음).
6. **규모:** 사용자 목록은 `users` 전체와 활성 `goals` 전체를 한 번씩 읽어 서버에서 합산한다(사용자 수만큼 반복 조회 없음). 수천 명 규모가 되면 집계 컬렉션이나 페이지 단위 조회가 필요하다.
7. 피드백 목록은 최대 200건(기본 100건)만 보이고 그 이상은 지시대로 페이지 처리가 없다.
8. 피드백 의견은 보관 기한이 정해지지 않았다(사용자가 지울 수 없는 데이터이므로 운영 정책이 필요).

## 11. 변경 파일

- 백엔드: `main.py`(관리자 의존성, 피드백·관리자 엔드포인트, 약관 v1.1, last_active 갱신), `schemas.py`, 신규 `tests/test_phase5e_admin.py`, 바꾼 기존 테스트(§6).
- 프론트 신규: `components/AdminUsersScreen.tsx`, `AdminFeedbackScreen.tsx`, `FeedbackCard.tsx`, `AccountIdCard.tsx`, `lib/adminLabels.ts`(+테스트). 수정: `app/page.tsx`(관리자 그룹 표시, 두 화면, 비관리자 해시 처리), `components/SettingsScreen.tsx`, `components/ConsentModal.tsx`, `lib/consent.ts`, `lib/viewHash.ts`, `app/globals.css`.
- 문서: `docs/erd_current.md`, `docs/phase1_design.md`(계약 항목만).

## 12. 커밋

테스트 통과 후 커밋·push 한다. `frontend/AGENTS.md`, `frontend/next-env.d.ts`, 비밀값은 포함하지 않는다. `backend/.env` 의 `ADMIN_UIDS` 는 사용자가 넣는다.

---

보고 후 멈추고 검증팀 검증을 기다립니다. 6B 이후는 시작하지 않았습니다.
