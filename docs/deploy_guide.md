# 배포 가이드 (사용자용: Vercel + Render + Firebase, 클릭 순서)

작성: 검증/PM, 2026-10-25. **개발팀의 Phase 7 작업(docs/phase7_dev_prompt.md)이 끝나고 PM 이 승인한 뒤에** 이 가이드를 따른다. 배포 사이트 화면 문구는 Render, Vercel 이 바꿀 수 있어 조금 다를 수 있다. 다르면 스크린샷을 보내 주면 PM 이 안내한다.

**원칙:** 비밀값(OpenAI 키, Firebase 서비스 계정, 관리자 ID 값)은 **채팅이나 문서에 붙여 넣지 않는다.** 입력은 콘솔에서 직접 한다. 확인이 필요하면 값이 아니라 "입력했다/됐다"만 알려 준다.

## 0. 시작 전에 알아 둘 것
| 항목 | 내용 |
|---|---|
| 구성 | 프론트(화면) = **Vercel**, 백엔드(API) = **Render**, 로그인과 DB = **Firebase**(이미 사용 중). 모두 같은 Firebase 프로젝트(`pace-mate`) |
| Render 무료 서버 | **15분 동안 접속이 없으면 잠들고**, 다시 깨우는 데 **약 1분** 걸린다(공식 문서). 그래서 첫 접속이 느리고 화면에 "서버를 준비하고 있습니다" 안내가 뜬다. 월 750시간 무료 |
| 비용 | OpenAI 호출만 사용량만큼 비용(키는 본인 것). Vercel, Render, Firebase(Spark)는 무료 범위 |
| 계정 | GitHub(저장소 `yong05610/ai-n-fprj`), Vercel, Render 에 각각 로그인할 수 있어야 한다. Vercel 과 Render 는 GitHub 로 로그인하면 저장소를 바로 연결할 수 있다 |
| 순서가 중요한 이유 | 프론트는 백엔드 주소를 알아야 하고, 백엔드는 프론트 주소(CORS)를 알아야 한다. 그래서 **① Vercel 에서 프론트 주소를 먼저 얻고 → ② Render 에 그 주소를 넣어 백엔드를 만들고 → ③ Vercel 에 백엔드 주소를 넣어 다시 배포**한다 |

## 1. Vercel: 프론트 만들기 (주소 얻기)
1. https://vercel.com 에서 GitHub 로 로그인한다.
2. **Add New… → Project** → 저장소 `ai-n-fprj` 옆 **Import**.
3. **Root Directory** 옆 **Edit**를 눌러 **`frontend`** 를 선택한다(중요: 저장소 루트가 아니라 frontend 폴더). Framework Preset 은 **Next.js** 로 자동 인식된다.
4. **Environment Variables** 에 아래를 추가한다(값은 `frontend/.env.local` 에서 복사. 이 값들은 공개 식별자라 비밀이 아니다).
   | 이름 | 값 |
   |---|---|
   | `NEXT_PUBLIC_AUTH_MODE` | `firebase` |
   | `NEXT_PUBLIC_FIREBASE_API_KEY` | `.env.local` 값 |
   | `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | `.env.local` 값 |
   | `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | `.env.local` 값 |
   | `NEXT_PUBLIC_FIREBASE_APP_ID` | `.env.local` 값 |
   | `NEXT_PUBLIC_API_BASE_URL` | **지금은 임시값** `https://example.invalid` (3단계에서 Render 주소로 바꾼다) |
5. **Deploy**. 끝나면 `https://<프로젝트이름>.vercel.app` 형태의 주소가 생긴다. 이 주소를 메모한다(이하 **프론트 주소**). 프로젝트 이름은 처음에 `pacemate` 처럼 짧게 지으면 주소가 간단하다.
6. 지금은 백엔드가 없어서 화면이 "배포 설정 오류" 또는 서버 연결 안내를 보여도 정상이다.
- **중요:** Vercel 환경변수는 **바꾼 뒤에 새로 배포(Redeploy)해야 반영**된다(공식 문서).

## 2. Render: 백엔드 만들기
1. https://render.com 에서 GitHub 로 로그인한다.
2. **New + → Web Service** → 저장소 `ai-n-fprj` 연결.
3. 아래처럼 입력한다.
   | 항목 | 값 |
   |---|---|
   | Name | `pacemate-api` (원하는 이름) |
   | Region | **Singapore** (한국에서 가장 가까운 곳) |
   | Branch | `main` |
   | **Root Directory** | **`backend`** |
   | Runtime / Language | **Python 3** |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
   | Instance Type | **Free** |
4. **Advanced** 를 열어 **Health Check Path** 에 `/health` 를 입력한다.
5. **Environment Variables** 에 아래를 추가한다. **값은 채팅에 붙이지 말고 콘솔에 직접 입력한다.**
   | 이름 | 값 | 비고 |
   |---|---|---|
   | `PYTHON_VERSION` | `3.12.10` | **필수.** Render 의 새 서비스 기본 Python 은 3.14 라서 지정하지 않으면 빌드가 달라질 수 있다 |
   | `AUTH_MODE` | `firebase` | |
   | `STORE_BACKEND` | `firestore` | |
   | `CORS_ORIGINS` | **프론트 주소** 그대로(예: `https://pacemate.vercel.app`) | 끝에 `/` 를 붙이지 않는다. `http://`, `localhost`, `*` 는 서버가 시작을 거부한다 |
   | `FIREBASE_SERVICE_ACCOUNT_JSON` | `backend/.env` 의 같은 이름 줄에서 `=` 뒤의 값 전체(한 줄) | 편집기로 `.env` 를 열어 값만 복사해 붙여 넣는다. 채팅에 붙이지 않는다 |
   | `OPENAI_API_KEY` | `backend/.env` 의 키 | 채팅에 붙이지 않는다 |
   | `API_DOCS_ENABLED` | `true` | 첫 확인용. 테스터 초대 전에 `false` 로 바꿀지 정한다(§6) |
   | `ADMIN_UIDS` | (지금은 비워 둠) | §5 에서 배포 사이트의 계정 ID 를 복사해 넣는다 |
   - **넣지 않는 것:** `RENDER`, `PORT` 는 Render 가 자동으로 설정한다. `AUTH_MODE=dev`, `STORE_BACKEND=memory` 는 배포에서 서버가 시작을 거부한다.
6. **Create Web Service**. 처음 빌드와 시작에 몇 분 걸린다. 로그에 `startup auth_mode=firebase store_backend=firestore` 가 보이면 성공이다.
7. 서비스 상단의 주소 `https://<이름>.onrender.com` 를 메모한다(이하 **백엔드 주소**).

## 3. 서로 연결하기
1. Vercel → 프로젝트 → **Settings → Environment Variables** 에서 `NEXT_PUBLIC_API_BASE_URL` 을 **백엔드 주소**(`https://….onrender.com`, 끝에 `/` 없음)로 바꾼다.
2. Vercel → **Deployments** → 최신 배포 오른쪽 **⋯ → Redeploy** (환경변수는 새 배포에만 반영된다).
3. Render 의 `CORS_ORIGINS` 가 **프론트 주소와 글자까지 같은지** 다시 확인한다(`https://` 로 시작, 끝에 `/` 없음, 공백 없음). 바꿨다면 Render 가 자동으로 다시 시작한다.

## 4. Firebase: 배포 도메인 허용
1. Firebase 콘솔 → **Authentication → 설정(Settings) → 승인된 도메인(Authorized domains)** → **도메인 추가** → 프론트 주소의 도메인 부분(`pacemate.vercel.app`, `https://` 없이)을 추가한다.
   - 공식 문서에서 익명 로그인에 이 설정이 필수인지는 확인하지 못했다. 추가해도 해가 없으므로 안전하게 추가한다.
2. 웹 API 키에 **HTTP 리퍼러 제한**을 걸어 둔 적이 있다면(Google Cloud 콘솔 → API 및 서비스 → 사용자 인증 정보) 프론트 주소도 허용 목록에 추가한다. 제한을 걸지 않았다면 건너뛴다.
3. **익명 로그인이 켜져 있는지** 확인한다(Authentication → 로그인 방법 → 익명 사용). 이미 로컬에서 쓰고 있으므로 켜져 있을 것이다.

## 5. 배포 사이트에서 확인하기 (PM 과 함께)
| 순서 | 할 일 | 정상 결과 |
|---|---|---|
| 5-1 | 브라우저로 `백엔드 주소/health` | `{"status":"ok","service":"pacemate-api","auth_mode":"firebase","store_backend":"firestore"}`. **첫 요청은 최대 1분** 걸릴 수 있다(서버가 깨어나는 중) |
| 5-2 | `백엔드 주소/docs` | API 문서 화면 |
| 5-3 | `프론트 주소` | "개발 모드" 띠가 **없다**. 약관(v1.1) 동의 창이 뜬다 |
| 5-4 | 동의 → 학습 하나 만들기 → 계획 확정 | 정상. Firestore 콘솔에 새 문서 |
| 5-5 | Render 대시보드에서 **Manual Deploy → Restart(또는 Deploy latest commit)** 후 새로고침 | 학습이 그대로 보인다(데이터 영속) |
| 5-6 | 15분 이상 접속하지 않고 다시 열기 | "서버를 준비하고 있습니다. 잠시만 기다려 주세요." 안내가 뜨고 약 1분 안에 정상 화면 |
| 5-7 | AI 튜터에 질문 | 답변과 출처/키워드. 첫 질문이 느려도 오류 없이 완료 |
확인 결과(통과/실패, 실패 화면 스크린샷, 브라우저 개발자도구 콘솔의 빨간 오류 줄)를 PM 에게 보내 준다. 통과하면 PM 이 `docs/pre_deploy_checklist.md` 와 TASK 7.4a~7.8 체크박스를 닫는다. 이때 미뤄 둔 화면 확인(5D, 5F, 6, 6B, 6C)과 모바일 폭도 함께 한다.

### 관리자 등록(배포 사이트에서 다시)
계정 ID 는 사이트 주소마다 따로 만들어진다. 로컬에서 복사한 ID 는 배포 사이트에서 다른 값이다.
1. **배포 사이트(프론트 주소)** 에서 동의한 뒤 [내 정보·설정] → **계정 ID 복사**.
2. Render → 서비스 → **Environment** 의 `ADMIN_UIDS` 에 그 값을 입력하고 저장한다(여러 명은 쉼표). Render 가 자동으로 다시 시작한다.
3. 배포 사이트를 새로고침하면 관리자 메뉴가 보인다.

## 6. 테스터를 초대하기 전에
1. **테스트 데이터 정리:** Firebase 콘솔 → Firestore → 데이터에서 개발 중 만든 컬렉션(`goals`, `tasks`, `study_logs`, `reflections`, `conversations`, `insights`, `users`, `consent_records`, `feedback`)의 문서를 정리한다. 컬렉션 오른쪽 **⋮ → 컬렉션 삭제**. **지우기 전에 PM 과 확인한다**(개발 계정이 쓰는 데이터와 10/22 확인 기록이 섞여 있다). 로컬과 배포가 같은 Firebase 프로젝트를 쓰므로 테스터 데이터와 개발 데이터가 섞이지 않게 하는 단계다.
2. **`/docs` 공개 여부:** 첫 확인이 끝나면 Render 의 `API_DOCS_ENABLED` 를 `false` 로 바꿔 API 문서를 닫을지 정한다(닫아도 서비스에는 영향 없다).
3. **접속 안내:** 테스터에게 줄 것은 프론트 주소 하나다. 첫 접속이 느릴 수 있다는 안내, 베타 서비스·AI 처리·개인정보·삭제 방법 설명(TASK 8.1)을 준비한다.
4. **OpenAI 비용 확인:** 사용량 한도를 설정해 두면 안전하다(OpenAI 대시보드의 Usage limits).

## 7. 문제가 생겼을 때
| 증상 | 가능한 원인과 확인 |
|---|---|
| 화면이 "서버에 연결하지 못했어요" | Render 가 잠들어 있거나 시작 실패. Render 로그를 확인하고 1~2분 기다린 뒤 재시도 |
| 브라우저 콘솔에 `blocked by CORS` | Render 의 `CORS_ORIGINS` 가 프론트 주소와 다르다(`/` 붙음, `http`, 오타). 고치면 자동 재시작 |
| 화면에 "배포 설정 오류: API 주소가 없어요" | Vercel 의 `NEXT_PUBLIC_API_BASE_URL` 이 비었거나 `http://`. 값을 고치고 **Redeploy** |
| Render 배포가 시작 직후 종료 | 로그의 마지막 줄이 이유다. 흔한 이유: `CORS_ORIGINS` 규칙 위반, `FIREBASE_SERVICE_ACCOUNT_JSON` 또는 `OPENAI_API_KEY` 누락(이름만 표시됨), Python 버전 |
| Render 빌드 실패(패키지 설치) | `PYTHON_VERSION` 이 `3.12.10` 인지 확인 |
| 모든 API 가 401 | 프론트와 백엔드가 서로 다른 Firebase 프로젝트를 가리킴. Vercel 의 `NEXT_PUBLIC_FIREBASE_*` 와 Render 서비스 계정 JSON 이 같은 프로젝트(`pace-mate`)인지 |
| 로그인 시 `unauthorized-domain` | §4 의 승인된 도메인에 프론트 도메인이 없음 |
| 환경변수를 바꿨는데 안 바뀜 | Vercel 은 Redeploy 필요, Render 는 저장하면 자동 재시작(안 되면 Manual Deploy) |
| 관리자 메뉴가 안 보임 | §5 의 관리자 등록을 **배포 사이트에서** 다시 한다 |

## 8. (선택) 암호로 다른 기기에서 이어 쓰기 켜기 (CR-005)
기본은 **꺼져 있다.** 켜지 않으면 화면과 서비스는 지금과 똑같고, 새 API 는 404 이다. 검증(PM)이 보안 확인을 마치고 사용자가 시간을 정한 뒤에만 켠다.
1. **비밀값 만들기.** 이 값이 비어 있거나 32자보다 짧으면 서버가 시작을 거부한다(메시지에는 변수 이름만 나온다). 터미널에서 아래 명령을 실행하고, 나온 한 줄을 **채팅에 붙이지 않고** Render 에 바로 붙여 넣는다.
   - Windows PowerShell: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   - 값은 코드, 문서, 채팅, 커밋 어디에도 쓰지 않는다. 안전한 곳(비밀번호 관리자)에도 따로 보관해 둔다.
2. Render → 서비스 → **Environment** 에 두 변수를 추가한다.
   | 이름 | 값 |
   |---|---|
   | `PASSWORD_LOGIN_ENABLED` | `true` |
   | `AUTH_PEPPER` | 위에서 만든 값 |
3. 저장하면 Render 가 자동 재시작한다. 로그에 `startup ...` 줄이 보이면 성공이다. 화면 쪽(Vercel)은 **아무것도 바꾸지 않는다**(서버의 `/health` 가 켜졌는지 알려 준다).
4. **`AUTH_PEPPER` 를 바꾸면 이미 등록된 모든 암호가 무효가 된다**(암호를 찾는 키가 달라지기 때문). 사용자는 [내 정보·설정]에서 암호를 다시 등록해야 하고, 다른 기기에서는 다시 들어올 수 없다. 꼭 필요할 때만 바꾼다.
5. 끄려면 `PASSWORD_LOGIN_ENABLED` 를 `false` 로 바꾼다(데이터는 그대로이고, 다시 켜면 이어진다).
6. 잠깐 멈추는 경우: 로그인 실패가 짧은 시간에 아주 많으면(전체 30회/10분 초과) 서버가 15분 동안 암호 로그인을 멈추고 Render 로그에 경고 한 줄(건수만)을 남긴다. 서버를 다시 시작하면 이 카운터는 초기화된다.
