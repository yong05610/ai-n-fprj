# Phase 7 검증 결과 (PM, 2026-10-25)

대상: 커밋 bc6ded1, 보고서 docs/phase7_report.md. 결론: **개발 범위 승인.** 배포 후에만 확인되는 항목은 미검증으로 남긴다.

## 직접 확인한 것
| 항목 | 방법 | 결과 |
|---|---|---|
| backend 테스트 | `python -m pytest` | 813 통과 |
| frontend 테스트·타입 | `npm test`, `npm run typecheck` | 152 통과, 오류 없음 |
| 프로덕션 빌드 | API 주소를 지정하고 `npm run build` | 성공 |
| 의존성 고정 | requirements.txt 7개가 `==` 이고, 이 PC 의 Python 3.12.10 venv 설치 버전과 일치. pytest·httpx 는 requirements-dev.txt 로 분리. 루트 `.python-version` = 3.12 | 일치 |
| Render 시작 검사 (RENDER=1 로 실제 import) | CORS 비움 / `*` / `http://` / 끝 `/` → 모두 시작 거부, 메시지에 **규칙 이름만** 있고 입력값 없음. 올바른 https 주소 → 시작 | 통과 |
| 비밀값 누락 | FIREBASE_SERVICE_ACCOUNT_JSON 비움 → 시작 거부, **변수 이름만** 표시 | 통과 |
| `/docs` 끄기 | `API_DOCS_ENABLED=false` → docs_url, openapi_url 이 None | 통과 |
| 화면 문구 | 서버 준비 안내와 배포 설정 오류 문구가 UTF-8 로 정상 저장 | 통과 |
| 코드 읽기 | `deploy_config.py`, `main.py` 변경, `coldStart.ts`, `deployConfig.ts`: 한도 8초/90초, 재시도 2·4·8초, 프로덕션에서 주소 없음·http 면 요청 차단 | 보고와 일치 |

## 보고서의 다음 주장은 코드와 단위 테스트까지만 확인함(브라우저 조작은 하지 않음)
- 콜드스타트 띠와 재시도 버튼, 대기 중 다른 요청 0건: 개발팀의 Chrome 확인을 믿지 않고, 배포 후 15분 방치한 실제 서버로 PM 이 확인한다.
- 화면 대조표 4개: 개발팀 표. PM 은 배포 URL 에서 화면을 직접 열 때 대조한다.

## 보고서와 다른 점·메모
- 개발팀이 지시서에 없던 예외를 하나 넣었다: 프로덕션 빌드에서도 `http://localhost` 는 설정 오류로 보지 않는다. 로컬에서 프로덕션 빌드를 시험하려는 목적이고, 배포 주소에서는 CORS 검사(B2)가 localhost 를 막으므로 **승인**.
- 개발팀의 "열린 결정" 4건에 대한 PM 판단: ① 대시보드 위젯별 요청 분리는 MVP 에서 하지 않는다(post_mvp 후보). ② 클라이언트 70/200초와 서버 제한 연동은 값을 바꿀 때만 같이 보면 되므로 문서 주의로 충분. ③ 모드 띠는 Firebase/Firestore 서버면 자동 숨김이라 그대로 둔다. ④ deploy_guide 에 반영함(아래).

## 미검증 (배포 후 PM 이 확인)
- Render(Linux)에서 설치·시작, `$PORT`, 시작 명령
- Render 요청 시간 제한 안에서 계획 생성(서버 60초 한도, 최악 180초) 실측
- 약 15분 방치 후 실제 콜드스타트 화면
- Vercel 빌드에 NEXT_PUBLIC_API_BASE_URL 이 들어가는지
- 모바일 폭, 튜터 실제 답변의 출처 표시
- 5D, 5F, 6, 6B, 6C 의 미뤄 둔 화면 확인

## 별도 대기
영어 입력 시 영어로 나오는 문제의 수정(docs/ops_fix_instructions_korean_output.md)은 개발 보고가 아직 없다. 보고가 오면 같은 영어 입력으로 6회 이상 실제 호출해 확인한다. 이 확인은 배포 전에 끝내는 것이 좋다.

---

# 추가 검증 — 배포 후 발견 2건 수정 (커밋 27e8abc, PM, 2026-10-25)
결론: **개발 범위 승인.** 실제 Render 가 잠든 상태에서의 확인은 배포 후 30분 방치 재검증으로 남긴다.

| 항목 | 방법 | 결과 |
|---|---|---|
| frontend 테스트·타입 | `npm test`, `npm run typecheck` | 160 통과(152 → 새 8), 오류 없음 |
| backend | 이 커밋은 backend 파일을 바꾸지 않음(파일 목록 확인) | 813 그대로 |
| 대시보드 순서 | diff 읽기: 종합 학습 현황 블록이 통계 카드 앞으로 이동, 문구 "아래 통계는…" | 목업과 일치 |
| 원인 | `useGoalSwitch` 가 실패를 삼키고 `goals=[]` 로 두어 "진행 중인 학습이 없어요" 를 그림. PM 추정(서버 깨우는 중 실패가 빈 상태로 보임)은 **절반만 맞았음**: api.ts 는 실패를 던지고 있었고, 빈 상태로 바꾼 곳은 이 훅 | 코드로 확인 |
| 수정 1 | `loadFailed` 상태 추가, `learningListView(loaded, loadFailed, n)` 로 오류와 빈 상태를 구분, 오류는 다시 시도 버튼 | 확인 |
| 수정 2 | `lib/api.ts` 한 곳에서 GET 만 `retryWhileWaking`(2/4/8초, 90초). 재시도 대상은 연결 실패, 시간 초과, 502/503/504 뿐이고 400/401/403/404/500 은 재시도하지 않음. 쓰기(POST/PATCH/DELETE)는 한 번만 보내 중복 저장 위험 없음 | 코드 확인 |
| 미확인 | 실제 Render 잠듦, 브라우저 화면(개발팀 Chrome 보고는 믿지 않고 배포 후 직접 확인), 대시보드·학습 실행·종합 분석의 같은 시나리오, 모바일 폭 | 배포 후 |

메모: `frontend/TASK.md`(untracked)는 루트 TASK.md 사본으로 보이며 PM 이 만든 것이 아니다. 커밋하지 않는다(혼동 방지를 위해 개발팀이 지우는 편이 좋다).