# Phase 8B 보고서 — 단계 A~B (읽기 스위치, 링크 검사)

작성: 개발팀, 2026-10-26. 기준: docs/phase8b_design.md, docs/phase8b_dev_prompt.md. 커밋 2개(45c1906, e30d761), **push 하지 않았다**. C~E 는 시작하지 않았다.

## 요약
- **A:** `RESOURCE_READ_SOURCE`(기본 `file`) 스위치와 읽기 경로, `allowed_domains.json`(34개), 후보·문서 저장 계층. 기본값에서는 사용자에게 달라지는 것이 없다(수정 전 코드의 결과와 대조해 증명).
- **B:** `link_checker.py`(SSRF 방어)와 `page_metadata.py`. 보안 시험을 항목별로 만들었고, 방어 코드를 일부러 망가뜨려 시험이 잡아내는지도 확인했다(아래 표 아래).
- 실제 외부 접속 **13회**(허용 도메인 12곳 + 없는 페이지 1회), **OpenAI 호출 0회**.

## 테스트
| 구분 | 결과 |
|---|---|
| backend pytest, 작업 전(HEAD 7b9fa5b) | 805 통과 + **8 실패** (합계 813) |
| backend pytest, 작업 후 | **1059 통과 + 8 실패** (새 테스트 254건: 읽기 스위치 57, 링크 검사 197) |
| frontend `npm test` / typecheck / build | 160 통과 / 통과 / 통과 (프론트 코드는 바꾸지 않음) |

**실패 8건은 이번 작업과 무관한 기존 실패다.** 작업을 시작하기 전 깨끗한 HEAD 에서 이미 같은 8건이 실패했다(`tests/test_phase5_exec.py`의 `TestStudyLogCrud`, `TestStudyLogIdempotency`, `TestReflection`, `TestDashboardSummary`). 원인: 테스트가 학습 기록 날짜를 `2026-10-19` 로 고정해 두었는데, 오늘이 10-26 이라 "최근 기록 조회" 기간 밖으로 밀려난다(날짜가 지나면서 깨진 테스트). 지시서 §0 에 따라 기대값을 고치지 않았다. **PM 이 고칠지 결정해 주세요.**(날짜를 오늘 기준 상대값으로 바꾸면 되는 종류로 보이지만 확인만 했고 고치지 않았다.)

## 단계 A

### 변경 요약
| 파일 | 내용 |
|---|---|
| `resources_catalog.py` | `load_catalog()` 가 `read_source()` 를 본다. `file`: 예전과 같은 `lru_cache` 목록(**같은 리스트 객체**)을 그대로 돌려주고 저장소를 읽지 않는다. `file+approved`: 승인 문서를 합쳐 60초 캐시, `invalidate_approved_cache()` 로 즉시 비움, 읽기 실패 시 파일만 사용 |
| `resource_store.py`(새) | `resource_candidates`·`learning_documents` 저장 함수. `get_store()` 인터페이스만 사용(메모리·Firestore 모두) |
| `resource_urls.py`(새) | `normalize_url`(중복 판정), `allowed_domains()` |
| `data/allowed_domains.json`(새) | `rag_documents.json` 의 도메인 **34개**를 스크립트로 추출(손으로 추가한 것 없음) |
| `backend/.env.example` | `RESOURCE_READ_SOURCE` 설명 한 줄(기본 file) |

### 읽기 스위치 동작
- 값은 호출마다 환경변수에서 읽는다. **정확히 `file+approved`(앞뒤 공백·대소문자 무시)일 때만** 합쳐 읽고, 오타나 다른 값은 모두 `file`(안전한 쪽)이다. 되돌릴 때는 환경변수만 `file` 로 바꾼다. 데이터는 바뀌지 않는다.
- 합칠 때: 파일 문서가 먼저, 같은 URL(정규화 기준)이나 같은 id 면 **파일 문서가 우선**. 승인 문서가 형식이 깨졌거나(필수 문자열 없음, https 아님, 태그 없음, `verified` 아님) 하면 건너뛴다. 승인 문서는 저장된 값과 무관하게 **항상 `link_only: true`, `chunks: []`** 로 읽는다 → 튜터 근거(`rag.py`)에는 들어가지 않고 참고 링크로만 나간다.
- 후보(`resource_candidates`)는 어떤 읽기 경로에도 나오지 않는다. `create_document` 는 승인·`link_only`·`doc_a_` id·https 인 완성 문서만 받고, 그 외는 `ValueError` 로 거부한다(후보를 `learning_documents` 에 쓰는 일을 코드로 막음).

### 시험 결과(읽기 스위치)
| 항목 | 증명 |
|---|---|
| `file` 모드 결과 불변 | 수정 **전 커밋**의 코드로 계산한 대표 입력 12개의 `match_references` 결과(`tests/fixtures/phase8b_golden_references.json`)와 수정 후 결과가 같음. 저장소에 승인 문서가 있어도 같음 |
| `file` 모드는 저장소를 읽지 않음 | 저장소 읽기 함수를 "호출되면 실패"로 바꿔도 통과, `load_catalog()` 가 매번 같은 리스트 객체 |
| `file+approved` 에서 승인 문서가 참고 링크에 나타남 | `match_references` 와 `GET /api/goals/{id}/references` 모두 확인 |
| 튜터 근거에는 안 나옴 | 승인 문서가 `rag` 색인에 없음, 튜터 검색 결과에도 없음. 저장된 `link_only: false`·청크가 있어도 무시됨 |
| Firestore 오류 시 파일만 | 오류를 던지게 해도 12개 대표 입력 결과 동일, API 200, 로그에는 예외 종류(`RuntimeError`)만 |
| 캐시 | 59초까지 이전 결과, 60초 후 갱신, 승인 직후 무효화 시 즉시 갱신, 실패는 10초 뒤 재시도 |
| 후보 비노출 | `pending` 후보가 `file+approved` 에서도 카탈로그·참고 링크에 나타나지 않음 |
| 되돌리기 | 같은 프로세스에서 환경변수만 `file` 로 바꾸면 바로 사라짐 |

### 설계에 없던 판단 (확인 부탁)
1. **실패 캐시 10초:** Firestore 가 느리거나 죽었을 때 모든 요청이 매번 기다리지 않도록, 읽기 실패 결과(=파일만)를 10초 동안 쓴다. 설계는 60초 캐시만 적었다.
2. **허용 도메인 파일의 `source_name`:** 카탈로그에서 한 도메인이 두 가지 이름으로 적힌 곳이 둘 있다 — `developer.mozilla.org`("MDN Web Docs" / "MDN Web Docs (Mozilla)"), `nextjs.org`("Next.js 공식" / "Next.js 공식 문서"). **카탈로그 파일에서 먼저 나온 이름**을 넣었다(`MDN Web Docs (Mozilla)`, `Next.js 공식 문서`). PM 이 통일할 이름을 정해 주세요.
3. 하루 상한·수집기 설정은 C 단계 범위라 만들지 않았다. `resource_store.count_candidates_created_on(day)` 는 Asia/Seoul 날짜로 세고 자동 반려도 센다(시험 있음).

## 단계 B

### 구성
- `link_checker.check_link(url, resolver=, fetcher=, is_duplicate=, clock=)` 는 예외를 던지지 않고 `LinkCheckResult`(통과 여부, 코드, 정규화 주소, 최종 주소, 도메인, source_name, 메타데이터, 단계별 결과 맵 `checks`)를 돌려준다.
- 외부로 나가는 함수는 둘뿐이고 모두 인자로 바꿀 수 있다: `resolve_host`(DNS), `fetch_head`(요청). 실제 요청 코드(`fetch_head`)는 가짜 연결을 넣어 읽기 한도·시간 한도 논리를 그대로 시험했다.
- **연결 고정:** `_PinnedHTTPSConnection` 은 검사한 IP 로만 `socket.create_connection((ip, 443))` 하고, TLS 서버 이름(SNI)과 Host 헤더는 원래 호스트명이다. 인증서 검증은 켜져 있다(`CERT_REQUIRED`, `check_hostname`). 연결 때 DNS 를 다시 묻지 않는다(시험에서 `getaddrinfo` 를 호출되면 실패하게 바꿔 증명).
- 응답 헤더 이름은 소문자화, 같은 헤더가 여럿이면 첫 값. `Accept-Encoding: identity`, 쿠키·인증 헤더 없음, User-Agent 고정(`PaceMateLinkCheck/1.0 ...`).

### 보안 시험 표 (모두 통과, 건수 = 시험 케이스 수)
| 지시서 항목 | 케이스 | 결과 코드 | 비고 |
|---|---|---|---|
| 형식: `http://`, `ftp://`, `file://`, `javascript:`, `data:`, `//host`, 사용자 정보(`a@b`, `user:pw@`, `docs.python.org@evil.com`), 포트 8443/80/99999/abc, 2048자 초과, 공백·탭·개행·널·역슬래시, 빈 값·`None` | 25(+통과 시험 5) | `bad_url` | 조회·요청 0회 확인. 조각(`#`) 제거, `:443`·대문자 호스트는 통과, 앞뒤 공백은 제거 |
| 허용 도메인 밖·위장: `evil.com`, `docs.python.org.evil.com`, `evil.com/docs.python.org`, `?next=docs.python.org`, `#@`, 하위 도메인, 상위 도메인, 끝 점(`docs.python.org.`), 키릴 문자 위장 2종, 전각 문자, 표의 마침표(`。`), punycode 2종 | 28 | `not_allowed_domain` | 조회·요청 0회. 34개 도메인은 정확 일치로 모두 통과 |
| 직접 IP 표기: `127.0.0.1`, `localhost`, 십진수 `2130706433`, 16진수 `0x7f000001`, 8진수 `0177.0.0.1`, `169.254.169.254`, `0.0.0.0`, `[::1]`, `[fc00::1]`, `[fe80::1]`, `[::ffff:127.0.0.1]` | (위 28건에 포함) | `not_allowed_domain` | 호스트가 허용 목록에 없으므로 DNS 까지 가지 않음 |
| **DNS 가 허용 도메인을 사설 주소로 돌려줌**: `127.0.0.1`, `10.0.0.1`, `172.16.0.1`, `172.31.255.255`, `192.168.0.1`, `169.254.169.254`, `169.254.0.1`, `0.0.0.0`, `255.255.255.255`, 멀티캐스트 `224.0.0.1`·`ff02::1`, 예약 `240.0.0.1`, 공유 `100.64.0.1`, 문서용 `192.0.2.1`, `198.18.0.1`, `::1`, `::`, `fc00::`, `fd12:3456::1`, `fe80::1`(+`%eth0`), IPv4 매핑 3종, NAT64·6to4·Teredo, IP 아닌 응답(`2130706433`, `0x7f000001`, `localhost`, `not-an-ip`, 빈 문자열) | 33 | `private_address` | **요청 0회** 확인 |
| **여러 주소 중 하나만 사설**(공인+사설 순서 둘 다, IPv6 사설 혼합 포함) | 4 | `private_address` | 요청 0회 |
| 공인 주소 통과(IPv4·IPv6·매핑된 공인) | 5 | 통과 | 연결에 쓴 IP 가 응답과 같음 |
| DNS 오류·빈 응답·DNS 시간 초과 | 4 | `dns_failed` ×3, `timeout` | |
| **DNS 리바인딩** | 4 | — | 한 홉에 DNS 조회 1회, 요청은 검사한 IP 로만(두 번째 조회가 사설 주소를 돌려줘도 사용 안 됨). 홉마다 자기 응답의 IP 로 연결. 실제 연결 클래스가 `(ip,443)` 으로 연결하고 SNI=호스트명, DNS 재조회 0회 |
| 리다이렉트: 허용 밖(`evil.com`, `//evil.com`, 위장 도메인), `http://`·`ftp://`·`javascript:`, 사설·직접 IP·`localhost`·`[::1]`, 사용자 정보, 포트 8443 | 13 | `bad_redirect` | 이동 대상은 조회도 요청도 하지 않음 |
| 리다이렉트: 허용 도메인이지만 DNS 가 사설 | 1 | `private_address` | 요청 안 함(홉마다 재검사) |
| 리다이렉트 횟수: 3번까지 통과, **4번째 거부**, 루프(a→b→a), 자기 자신, 정규화하면 같은 주소 | 3 | 통과 / `bad_redirect` | 4번 거부 시 요청 4회에서 중단 |
| 리다이렉트: 허용 도메인 안 이동, 상대 경로, 5가지 상태(301·302·303·307·308) | 7 | 통과 | 최종 주소 보고 |
| `Location` 없음 | 1 | `bad_status` | |
| 시간·크기: 연결 3초 상한(남은 시간이 더 적으면 그 값), 이미 지난 기한, **바이트를 천천히 보내는 서버**(읽을 때마다 3초) → 8초 상한에서 끊김, 응답 헤더가 느림, 소켓 시간 초과 | 6 | `timeout` | 가짜 시계로 시험 |
| **128KB 초과: 앞 128KB 만 읽고 중단**, 나머지는 요청하지 않음(끝없는 스트림에서 정확히 131072바이트만 소비, 한 번에 8KB 이하) | 2 | 통과 | 큰 페이지도 머리 부분 메타데이터가 나옴 |
| 요청 오류 매핑: 소켓 시간 초과 2종, 인증서 오류·연결 거부·재설정·잘못된 상태줄·중간 끊김, 너무 긴 헤더(요청 단계와 응답 단계 양쪽) | 8 | `fetch_failed` / `too_large` | 연결은 항상 닫힘 |
| 연결 실패면 다음 검사된 주소를 시도, 시간 초과면 멈춤 | 1 | — | |
| 응답 상태: 201·204·206·400·401·403·404·410·429·500·502·503 | 12 | `bad_status` | |
| `Content-Type`: pdf, json, octet-stream, text/plain, image/png, xhtml, 없음, `html` | 8 | `bad_type` | `text/html` 의 대소문자·charset 변형 4종은 통과. gzip 등 압축 응답은 `bad_type` |
| 빈 본문·공백뿐 | 2 | `empty_body`(추가 코드) | |
| 중복: 카탈로그 링크의 네 가지 표기(끝 `/`, 대소문자, `utm_*`·`fbclid`, 조각), 대기·승인 후보, 최종 주소가 중복 | 4 | `duplicate` | 반려된 후보는 중복 아님. **중복이면 DNS·요청 0회** |
| 메타데이터 파서 | 10 | — | `<title>` 없음, 200/500자 자르기, 제어문자·양방향 제어·0폭 문자 제거, **`<script>`·`<img onerror>` 가 든 제목은 문자열 그대로**(변환·실행 없음), og: 대체와 일반값 우선, 스크립트·본문 안의 가짜 meta 무시, EUC-KR 등 문자 집합(헤더·meta), 깨진 HTML 에도 예외 없음 |
| **로그** | 1 | — | 통과·거부 모두 `caplog` 에 제목·설명·주소·호스트가 없고 코드·단계·리다이렉트 횟수만 남음 |

### 시험이 정말 잡아내는지(변이 시험)
방어 코드를 하나씩 일부러 망가뜨리고 같은 시험을 돌렸다. 잡아낸 것: 사설 주소 검사 제거(34건 실패), 허용 도메인 검사 제거(33건), 연결을 IP 가 아닌 호스트명으로(1건), 리다이렉트 루프 검사 제거, 리다이렉트 횟수 제한 해제, 사용자 정보(`@`) 검사 제거(4건), 시간 한도 해제, 멀티캐스트 검사 제거. 잡지 못한 2건은 **동등한 변이**였다: ① 128KB 루프 조건(`min(...)` 이 이미 0바이트 읽기로 멈추게 함), ② IPv4 매핑 처리(이 환경의 Python 3.12.10 은 `::ffff:127.0.0.1` 을 스스로 비공인으로 판정하므로 결과가 같다. 코드는 Python 버전에 기대지 않도록 명시적으로 풀어 두었다).

### 실제 확인 (지시서 §34; 실제 외부 접속 13회, OpenAI 0회)
방법: 실제 DNS·실제 TLS·실제 `fetch_head` 로 카탈로그 링크 1개씩 `check_link`(중복 검사만 끔). **같은 컴퓨터(로컬)에서 한 번씩** 측정했다.
| 도메인 | 결과 | 제목(앞부분) | 설명 | 리다이렉트 | 시간 |
|---|---|---|---|---|---|
| docs.python.org | 통과 | The Python Tutorial — Python 3.15.2 documentation | 200자 | 없음 | 0.31초 |
| developer.mozilla.org | 통과 | JavaScript 첫걸음 \| MDN | 192자 | **1번(허용 도메인 안, 최종 주소 보고됨)** | 1.39초 |
| ko.javascript.info (한국어) | 통과 | 모던 JavaScript 튜토리얼 | 82자 | 없음 | 1.17초 |
| ko.react.dev (한국어) | 통과 | 빠르게 시작하기 – React | 46자 | 없음 | 0.22초 |
| web.dev | 통과 | Learn web development \| web.dev | **없음** | 없음 | 0.80초 |
| nextjs.org | 통과 | App Router | 143자 | 없음 | 0.91초 |
| www.opentutorials.org (한국어) | 통과 | 생활코딩 | **없음** | 없음 | 1.92초 |
| learn.microsoft.com | 통과 | C# 문서 … Microsoft Le(…) | 52자 | 없음 | 0.59초 |
| go.dev | 통과 | A Tour of Go | **없음** | 없음 | 0.45초 |
| docs.docker.com | 통과 | Get started \| Docker Docs | 120자 | 없음 | 0.36초 |
| fastapi.tiangolo.com | 통과 | FastAPI - FastAPI | 86자 | 없음 | 0.25초 |
| www.postgresql.org | 통과 | PostgreSQL: Documentation: 18: Part I. Tutorial | 162자 | 없음 | 2.02초 |
| (없는 페이지 `docs.python.org/3/...`) | `bad_status` | — | — | — | — |
- **12곳 모두 제목이 나왔다.** 설명이 없는 곳이 셋(web.dev, opentutorials, go.dev)이다 → 이 도메인의 후보는 AI 제안이 제목과 도메인에만 의존한다(관리자가 직접 보완). 봇을 막거나 JavaScript 로 제목을 만드는 도메인은 이 12곳에서는 없었다. 나머지 22개 도메인은 확인하지 않았다(**미확인**).
- 사이트마다 제목에 사이트 이름이 붙는다("… | MDN"). 그대로 저장하며 정리하지 않았다.

## 계약·문서
- DTO·API 변경 없음(A~B 는 내부 모듈). `schemas.py`, `erd_current.md`, `phase1_design.md`, 프론트 타입은 건드리지 않았다.
- 새 환경변수: `RESOURCE_READ_SOURCE`(기본 `file`). `backend/.env.example` 에만 설명했다. `backend/.env` 는 건드리지 않았다.

## 설계·지시서와 다르게 한 곳 / 판단
| # | 내용 | 이유 |
|---|---|---|
| 1 | **중복 검사를 DNS·요청 앞으로 옮겼다**(형식·도메인 다음). 설계 표에서는 8번째. 최종 주소도 한 번 더 검사 | 이미 있는 링크에 외부 요청을 보낼 이유가 없고, 통과·거부 결과는 같다. 설계 순서대로가 좋다면 알려 주세요 |
| 2 | **128KB 초과는 거부(`too_large`)가 아니라 "앞 128KB 만 읽고 중단"**. `too_large` 는 응답 헤더가 한도를 넘을 때만 | 실제 문서 페이지는 128KB 를 넘는 것이 흔하고 제목·설명은 앞쪽에 있다. 지시서 문구("128KB 초과 시 중단, 본문 전체를 읽지 않음")대로 해석했다. 큰 페이지를 거부하길 원하면 알려 주세요 |
| 3 | 설계 코드 목록에 없던 코드 추가: `dns_failed`, `fetch_failed`(연결·TLS·프로토콜 오류), `empty_body` | 설계의 코드만으로는 이 실패들이 이름을 갖지 못함 |
| 4 | 호스트는 **ASCII 만** 인정(유니코드 호스트는 IDNA 변환 없이 `not_allowed_domain`). 끝 점(`docs.python.org.`)도 거부 | 허용 목록이 모두 ASCII 이므로 잃는 것이 없고, 전각·키릴 위장이 변환으로 허용 호스트와 같아지는 길을 아예 없앤다 |
| 5 | 압축된 응답(`Content-Encoding` ≠ identity)은 `bad_type` | `Accept-Encoding: identity` 로 요청하므로 정상 서버는 압축하지 않는다. 압축 해제는 폭탄(zip bomb) 방어가 더 필요해 하지 않았다. 12곳 모두 문제없었다 |
| 6 | DNS 조회 시간 상한은 3초(연결 상한과 같음), 전체 8초는 연결·응답·읽기에 적용. DNS 시간은 전체 8초에 합산하지 않는다 | `getaddrinfo` 는 취소할 수 없어 스레드에서 기다리다 포기한다(스레드는 남을 수 있음). 최악 시간은 홉당 DNS 3초 + 요청 8초 |
| 7 | IPv6 로만 열리는 서버는 Render 에서 연결이 안 될 수 있어, 한 호스트의 **검사된 주소 여러 개를 차례로** 시도한다 | 연결 거부일 때만 다음 주소, 시간 초과면 멈춤 |

## 미검증
- **Render 무료 서버에서의 외부 읽기 시간**(설계 §6 두 번째 가정). 위 시간은 로컬 측정이라 배포 환경을 대신하지 못한다.
- 나머지 22개 허용 도메인의 메타데이터 제공 여부.
- Firestore 실연동: 저장 계층은 메모리 저장소로만 시험했다(`find` 의 단일 동등 조건과 `set/get/update` 만 써서 Firestore 에서 복합 색인이 필요하지 않게 했으나 실제 Firestore 에서는 확인하지 않음).
- `file+approved` 모드의 사용자 API·튜터 화면은 단위·API 수준 시험만(브라우저 확인은 D 이후 계획에 포함).
- 동시에 여러 요청이 들어올 때의 DNS 스레드 풀(4개) 거동.

## 열린 결정 (PM)
1. 위 "판단" 1~2, 4~5 중 되돌리고 싶은 것.
2. 기존 8건 실패 테스트(날짜 고정)를 누가 어떻게 고칠지.
3. `source_name` 이 둘인 두 도메인(MDN, Next.js)의 이름 통일.
4. SSRF 검증(PM) 후 C 단계 시작 여부.

## 커밋
- 45c1906 `feat: Phase 8B step A ...`, e30d761 `feat: Phase 8B step B ...` (push 안 함). `frontend/AGENTS.md` 는 커밋에 넣지 않았다.
