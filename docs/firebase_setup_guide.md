# Firebase 설정 가이드 (사용자 직접 진행)

목적: Phase 3부터 dev 모드로만 검증한 인증(익명 로그인)과 Firestore 저장을 실제 Firebase 로 연결해 검증한다.
원칙: 모든 값은 같은 Firebase 프로젝트에서 가져온다. 비밀값은 채팅, 문서, 커밋에 붙여넣지 않고 .env 파일에만 입력한다.

## 0. 준비
- Firebase 콘솔: https://console.firebase.google.com
- 사용할 프로젝트를 하나 정한다(이미 PROJECT_ID 를 발급받은 프로젝트를 그대로 쓴다).
- 프로젝트 이름과 PROJECT_ID 를 기억해 둔다. 아래 모든 단계에서 같은 프로젝트인지 확인한다.

## 1. 익명 로그인 켜기
1. 왼쪽 메뉴 Build → Authentication → 시작하기
2. 로그인 방법(Sign-in method) 탭 → 익명(Anonymous) → 사용 설정 → 저장

## 2. Firestore 데이터베이스 만들기
1. Build → Firestore Database → 데이터베이스 만들기
2. 모드: 프로덕션 모드로 시작(기본 거부). 서버(Admin SDK)는 규칙을 우회하므로 서비스 동작에는 영향이 없다.
3. 위치: asia-northeast3 (서울) 권장. 한 번 정하면 바꿀 수 없다.

## 3. 웹 앱 등록 후 프론트 설정값 입력
1. 프로젝트 설정(톱니바퀴) → 일반 → 내 앱 → 웹(</>) 아이콘으로 앱 추가(Firebase Hosting 설정은 체크하지 않는다)
2. 화면에 나오는 firebaseConfig 의 값을 frontend/.env.local 에 입력한다.
   - NEXT_PUBLIC_FIREBASE_API_KEY=apiKey 값
   - NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=authDomain 값
   - NEXT_PUBLIC_FIREBASE_PROJECT_ID=projectId 값
   - NEXT_PUBLIC_FIREBASE_APP_ID=appId 값
3. 이 값들은 공개 식별자이며 비밀값이 아니다. 따옴표와 공백 없이 한 줄씩 입력한다.

## 4. 서비스 계정 키를 백엔드에 입력
1. 프로젝트 설정 → 서비스 계정 → 새 비공개 키 생성 → JSON 파일 다운로드
2. 그 JSON 파일의 전체 내용을 한 줄로 만들어 backend/.env 에 입력한다.
   - FIREBASE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"...", ... }
   - 줄바꿈이 있으면 안 된다. 개인키 안의 \n 은 그대로 둔다(글자 그대로 백슬래시 n).
3. 다운로드한 JSON 파일은 저장소 밖(예: 문서 폴더)에 보관하거나 입력 후 삭제한다. 저장소 안에 두지 않는다. (.gitignore 가 일부 이름은 막지만 의존하지 않는다.)
4. 이 키는 프로젝트 전체 권한을 가지므로 채팅, 문서, 커밋에 절대 붙여넣지 않는다.

## 5. 모드 전환 (검증 시점에)
개발팀이 dev 모드로 작업 중이면 개발팀 작업이 끝난 뒤에 바꾼다.
- backend/.env: AUTH_MODE=firebase, STORE_BACKEND=firestore
- frontend/.env.local: NEXT_PUBLIC_AUTH_MODE=firebase
- 서버는 --env-file .env 로 재시작한다. 프론트는 npm run dev 를 재시작한다.

## 6. 보안 규칙 (선택, 우선순위 낮음)
- 서버가 Admin SDK 로만 접근하므로 서비스 동작에는 규칙이 필요하지 않다. 프로덕션 모드 기본값(전체 거부)이 이미 안전하다.
- 저장소의 firebase/firestore.rules 를 적용하려면: Firestore Database → 규칙 탭에 파일 내용을 붙여넣고 게시한다.
- firebase/firestore.indexes.json 의 복합 인덱스는 현재 코드가 사용하지 않는다(정렬을 서버에서 처리). 지금은 만들지 않아도 된다. 나중에 쿼리 정렬을 Firestore 로 옮길 때 필요하다.

## 7. 확인 방법 (설정 후)
- 위 입력이 끝났다고 검증팀에 알린다. 값은 보내지 않는다.
- 검증팀이 키 존재 여부를 값 출력 없이 확인하고, 실제 인증과 저장 흐름(동의 → 익명 UID → 목표 저장 → 타 UID 격리 → 데이터 삭제)을 검증한다.
- Firebase 콘솔 Authentication → 사용자 탭에 익명 사용자가 생기고, Firestore Database → 데이터 탭에 users, consent_records, goals 문서가 생기면 정상이다.

## 8. 문제 해결
- 서버 시작 시 AUTH_NOT_CONFIGURED 또는 503: FIREBASE_SERVICE_ACCOUNT_JSON 이 비었거나 JSON 이 깨진 경우. 한 줄인지, 따옴표가 유지됐는지 확인한다.
- 모든 요청이 401: 프론트와 백엔드가 서로 다른 Firebase 프로젝트를 가리키는 경우가 많다. PROJECT_ID 를 양쪽에서 비교한다.
- 익명 로그인 오류(프론트): 1단계에서 익명 로그인을 켰는지, .env.local 값이 맞는지 확인한다.
- Firestore 권한 오류: 서비스 계정이 해당 프로젝트의 키인지 확인한다.
