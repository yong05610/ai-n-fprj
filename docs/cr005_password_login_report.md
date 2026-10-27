# CR-005 보고서 — 암호로 다른 기기에서 이어 쓰기

작성: 개발팀 세션, 2026-10-28. 지시서: `docs/cr005_password_login_dev_prompt.md`. **커밋만 했고 push 하지 않았다.**

## 1. 결과 요약
- 완료. 기본 꺼짐(`PASSWORD_LOGIN_ENABLED` 없음/false)이면 새 API 는 404, `/health.password_login_enabled=false`, 화면에 새 카드·링크 없음 → 지금 배포에 올라가도 사용자에게 달라지는 것이 없다.
- 테스트: **pytest 1346건 통과**(기존 1264 + 신규 82), **npm test 204건 통과**(기존 183 + 신규 21), `npm run typecheck`, `npm run build` 통과.
- 이어받기: 2026-10-27 작성분을 `git status`/`git diff` 로 확인해 이어서 마무리했다(처음부터 다시 만들지 않음). 아래 §9 의 "내가 만들지 않은 수정"은 커밋에서 제외했다.

## 2. 변경 요약
| 영역 | 파일 | 내용 |
|---|---|---|
| 백엔드 | `password_auth.py`(신규) | 규칙 검사, 흔한 암호 거부, scrypt 키, 시도 제한(메모리), IP 판별, 시작 검사 |
| | `main.py` | `POST/DELETE /api/auth/password`, `POST /api/auth/password/login`, profile·`/health` 필드, `delete-data` 가 `credentials` 삭제, 시작 시 `assert_safe_password_config()` |
| | `auth.py` | `create_login_token(uid)`: firebase `create_custom_token`, dev 는 `dev-<uid>` |
| | `schemas.py` | `PasswordSetRequest`, `PasswordStatusResponse`, `PasswordLoginRequest/Response`, `UserProfileResponse` 에 `password_enabled`, `password_set_at`, 새 오류 코드 주석 |
| | `data/common_passwords.txt`(신규) | 흔한 암호 4,000개(§5) |
| 규칙 | `firebase/firestore.rules` | `credentials` 읽기·쓰기 전부 불가를 명시 |
| 프론트 | `lib/passwordLogin.ts`(신규), `lib/session.ts`, `lib/modeBanner.ts` | 규칙 표시 로직, 로그인 흐름(의존성 주입), `signInWithPasswordToken`(dev/firebase), `/health` 플래그 해석 |
| | `components/PasswordForms.tsx`, `PasswordCard.tsx`(신규), `ConsentModal.tsx`, `AuthProvider.tsx`, `ServerGate.tsx`, `SettingsScreen.tsx`, `app/page.tsx`, `app/globals.css` | 설정 카드, 동의 창 링크, `loginWithPassword`/`logout`, 규칙 목록 스타일 |
| 문서 | `docs/phase1_design.md`(API 표), `docs/erd_current.md`(규칙 절 글만, **도형 미수정**), `docs/deploy_guide.md` §8, `README.md`, `backend/.env.example` | 계약·배포 안내 |
| 시험 | `tests/test_cr005_password_login.py`(신규 82), `lib/passwordLogin.test.ts`(신규 21) | |

**기존 시험 수정(지시서 1-5 에 따른 이유 보고):** `/health` 응답에 새 필드가 생겨 기대값이 정확히 일치하던 시험 3곳에 `password_login_enabled` 만 더했다(`test_health_and_docs.py`, `test_phase7_deploy.py`, `test_ops_mode_visibility.py` 의 키 집합). 그 밖의 기존 시험은 그대로 통과한다.

## 3. API / DTO 변경
| API | 인증 | 변경 |
|---|---|---|
| `POST /api/auth/password` | 동의한 UID | 신규. `{password, client_request_id}` → `{password_enabled, password_set_at}`. 422 `PASSWORD_RULE`, 409 `PASSWORD_UNAVAILABLE`, 429 `TOO_MANY_ATTEMPTS`, 꺼짐 404 |
| `DELETE /api/auth/password` | 동의한 UID | 신규. 키 삭제, `password_enabled=false`, 없어도 200 |
| `POST /api/auth/password/login` | 없음 | 신규. `{password}` → `{custom_token}`; 401 `LOGIN_FAILED`, 429, 꺼짐 404 |
| `GET /api/user/profile` | 기존 | `password_enabled`, `password_set_at` 추가 |
| `GET /health` | 없음 | `password_login_enabled` 추가 |
| `POST /api/user/delete-data` | 기존 | 이 UID 의 `credentials` 문서도 삭제 |

저장: `credentials/{key}` = `{uid, created_at}`(+저장소가 붙이는 `id`=key). `users` 에는 `password_enabled`, `password_set_at` 만(키·해시 없음). `USER_OWNED_COLLECTIONS` 에 넣지 않았다.

## 4. §5 시험 결과 (항목별)
| # | 항목 | 결과 | 시험 |
|---|---|---|---|
| 1 | 꺼짐: 새 API 404, health false, 기존 시험 통과 | 통과 | `TestOffByDefault`(값 6종), 전체 1346 |
| 2 | 등록→토큰 없이 로그인→같은 UID→기존 목표 조회 | 통과 | `TestRegisterAndLogin` |
| 3 | 규칙 10종 422, 흔한 암호·패턴 9종 409 같은 문장 | 통과 | `TestRules` |
| 4 | 겹침 409, 문장이 흔한 암호 거부와 **응답 본문 전체 동일**, A 키·B 데이터 불변 | 통과 | `TestOverlap` |
| 5 | 변경 후 옛 암호 401·새 암호 200, 끄기 후 401·`password_enabled=false` | 통과 | `TestChangeAndOff` |
| 6 | 멱등: 같은 `client_request_id` 재시도 200, 키 문서 1개 | 통과 | `TestIdempotency` |
| 7 | IP 6번째 실패 후 429·다른 IP 계속, 전체 31번째 후 모두 429, 시계 이동으로 해제, 등록 제한(UID 5, IP 10/시간) | 통과 | `TestAttemptLimits`(시계 주입) |
| 8 | 실패·성공 시간 | 구조 시험으로 대체 | 모든 시도에서 해시 계산, 실패에만 고정 지연 호출, 규칙 위반 입력도 같은 401·같은 본문(`TestTiming`). 실측은 §6 |
| 9 | delete-data 후 로그인 401, `credentials` 0개 | 통과 | `TestDeletion` |
| 10 | 비노출: caplog·응답·users 문서·검증 오류·예외 경로에 암호·키 없음 | 통과 | `TestNoLeak` |
| 11 | `PASSWORD_LOGIN_ENABLED=true` + 펩퍼 없음/31자 → 시작 거부(값 미표시), 새 프로세스 `import main` 도 거부 | 통과 | `TestStartupCheck` |
| 12 | 타 UID 격리 | 통과 | `TestIsolation` |
| 13 | 프론트: 카드 표시 조건, 체크박스 전 비활성, 규칙 문자 표시, 동의 창 링크, 실패 문구, 익명 로그인 미호출, 로그아웃 확인 | 통과 | `lib/passwordLogin.test.ts` 21건 |

## 5. 흔한 암호 목록
- 출처: **SecLists**(https://github.com/danielmiessler/SecLists), 저장소 라이선스 **MIT**(Copyright (c) 2018 Daniel Miessler; LICENSE 파일을 직접 내려받아 확인). `Passwords/Common-Credentials/Pwdb_top-1000000.txt` 와 `xato-net-10-million-passwords-1000000.txt` 에서 **이 규칙을 통과할 수 있는 형태(8~64자 ASCII, 영문·숫자·특수문자 포함)만, 빈도 순으로 각 2,000개 → 4,000개**. 머리 주석에 출처·라이선스를 적었다. 비교는 대소문자 무시.
- 주의(PM 판단 필요): 저장소는 MIT 이지만 목록 자체는 공개 유출 데이터에서 모은 암호 모음이다. 개인 식별 정보(아이디·주소)는 들어 있지 않다.
- 패턴 거부: 같은 문자 4번 이상, 키보드·숫자·알파벳 연속 4자(역순 포함), `pacemate`/`password`/`passw0rd` 포함(치환 `0→o`, `1→i/l`, `@→a`, `$→s` 적용). 예: `P@$$w0rd1` 도 거부. 치환 목록에 없는 `4→a` 등은 적용하지 않는다(지시서 범위).

## 6. 실제 확인
| 항목 | 결과 |
|---|---|
| dev 모드, Chrome 2창(일반·새 컨텍스트) 27개 점검 | 전부 통과: 동의 창 링크, 등록 전 버튼 비활성·체크 후 활성, 규칙 "충족" 글자, 등록, 다른 창에서 틀린 암호 문구·맞는 암호 로그인(**같은 UID, 같은 목표**, 동의 재요청·익명 시작 없음), 바꾸기(옛 암호 401), 끄기(401), 로그아웃 확인 문구·재로그인, 설정의 전환 경고, 375px 가로 넘침 없음, 브라우저 저장소에 암호 없음, 페이지 오류 0 |
| **firebase 모드**(`backend/.env` 그대로 + `PASSWORD_LOGIN_ENABLED`, `AUTH_PEPPER` 만 덮어씀), 새 시험용 익명 사용자 1명 | 등록 → 새 컨텍스트에서 암호 로그인 → `signInWithCustomToken` 으로 **같은 UID**, 새로고침 후에도 같은 UID. 끝나서 그 사용자로 앱의 데이터 삭제를 실행 → 같은 암호 로그인 401(키 삭제 확인). 실제 사용자 데이터는 건드리지 않음 |
| 해시 시간(이 PC) | scrypt 중앙값 **50ms**(47~59) |
| 로그인 응답(이 PC, 서버 내부) | 성공 59~72ms, 실패 362~371ms(= 해시 + 고정 지연 300ms) |
| 서버·포트 | 3123/8123 에 띄웠고 끝나서 종료. 비밀값은 출력하지 않았다 |

주의: 실패 응답은 성공보다 약 300ms 느리다(지시서 "실패 시 고정 지연을 더한다"). 상태 코드로 이미 알려지는 차이이며, 의도는 실패 사유(틀림/규칙 위반 등) 사이의 시간 차이를 없애는 것이다.

## 7. IP 판별
Render(`RENDER` 환경변수 있음): `X-Forwarded-For` 의 **가장 오른쪽 값**(Render 프록시가 붙인 값, 클라이언트가 왼쪽에 넣은 값은 믿지 않음). 그 밖: `request.client.host`. IP 는 메모리 카운터에만 있고 로그·저장소에 쓰지 않으며 만료된 항목은 삭제한다. **배포 후 실제로 그 값이 클라이언트 IP 인지 PM 확인이 필요하다.** 사용자 한 명이 NAT 뒤 여러 사람과 같은 IP 를 쓰면 함께 차단될 수 있다.

## 8. 화면 비교표 (§3, 기존 카드와 나란히)
| 요소 | 기존 `FeedbackCard`(+`DeleteDataSection`) | 새 `PasswordCard` |
|---|---|---|
| 컨테이너 | `section.card`, `marginTop:13`(Feedback) | 같음 `section.card#password-card`, `marginTop:13` |
| 제목/설명 | `h2` + `p.small.muted` | 같음 |
| 입력 | `div.field > label + input` | 같음 (`type=password`, `autocomplete=new-password`) |
| 규칙 안내 | — | `ul.pw-rules`(새 클래스, "충족/필요" 글자 + 색) |
| 확인 체크박스 | 동의 창의 `label.consent-check` | 같은 클래스 |
| 상태 문구 | `p.small[role=status]` 초록 | 같음 |
| 오류 | `p.error[role=alert]` | 같음 |
| 버튼 | `.btn`, `.btn.secondary`, `.btn.danger` | 같음 |
| 확인 창 | `.modal-backdrop > .modal`, `.modal-actions`(Delete) | 같음 |
| 링크 | `.link-btn` | 같음 |
| 동의 창 | `ConsentModal` 하단 | `p.small` 안에 `button.link-btn` "이미 암호를 등록했어요(사용자 인증)" 추가, 누르면 같은 `.modal` 안에서 `PasswordLoginForm` |
새 CSS 는 `.pw-rules`(3줄)뿐이다. 목업 반영은 PM.

## 9. 미검증 / 한계 / 열린 결정
- **내가 만들지 않은 수정:** `서비스기획서.md` 에 작업 폴더 수정이 있다(제목 줄 끝 공백·빈 줄 제거, "개발 기간: 총 14일" → "개발 기간:" 으로 비움 등 3줄). 이 세션에서 한 일이 아니며(IDE 에서 열려 있던 파일) 설계 문서라 **커밋에 포함하지 않고** 그대로 두었다. 되돌릴지는 PM 이 정한다.
- Render 무료 서버의 해시·로그인 시간, 배포 후 IP 판별: PM 측정/확인 필요.
- 시도 제한 카운터는 메모리라 서버 재시작 시 초기화되고(단일 인스턴스 기준) 인스턴스가 둘이면 각각 센다.
- 같은 키를 두 UID 가 **동시에** 등록하는 경쟁은 저장소에 트랜잭션이 없어 완전히 막지 못한다(쓴 뒤 다시 읽어 다른 UID 면 409 로 거절해 줄였지만 극단적 동시성은 미검증).
- `delete-data` 응답에는 삭제 목록 필드가 원래 없어(상태·메시지만) "삭제 목록에 표시"는 하지 않았다. 필요하면 DTO 변경이 필요하므로 결정 요청.
- `AUTH_PEPPER` 를 바꾸면 등록된 모든 암호가 무효가 된다(`docs/deploy_guide.md` §8, `.env.example` 에 적음).
- 모바일은 375px 가로 넘침만 확인했고 실제 휴대폰은 미확인. 로그인 중 로그인 폼 화면은 Firebase 실서버 동작을 시험용 사용자 1명으로만 확인.
- Firestore 보안 규칙(`credentials` 거부)은 파일에만 추가했고 콘솔 배포는 하지 않았다(사용자 작업).
- 열린 결정: ① 동의 문구/약관 버전에 암호 안내 추가 여부(지시서대로 v1.1 불변), ② 암호 로그인 실패 시 알림(경고 로그 한 줄만 구현), ③ 흔한 암호 목록의 출처 사용 가능 여부.
