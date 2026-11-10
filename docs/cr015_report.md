# CR-015 보고서 — 글자 크기 상향(동적 글만)

작성: 개발팀, 2026-11-10. 지시서: `docs/cr015_dev_prompt.md`(근거 `docs/cr015_font_size_design.md`). 변경은 `frontend/app/globals.css` 한 파일의 `font-size` 값(76곳)과 `.goal-switch label` 의 `white-space: nowrap` 뿐이다. 레이아웃·색·문구·12px 이상 크기·CR-014 `.task-desc`(12px) 는 바꾸지 않았다. TSX 의 인라인 `fontSize` 는 없다(0건).

## 1. 바꾼 방식
값을 직접 수정했다(CSS 변수 없음). 한 번에 다시 조정하려면 아래 표의 매핑만 바꾸면 되도록 선택자별로 정리했다. 크기 분포(px): 전 `8:15 9:26 10:34 11:18` → 후 `8:1 9:9 10:20 11:18 12:56`(남은 8~10px 은 모두 ⓑ 고정 안내 주석).

## 2. 분류표
목업 `<style>` 의 변경(65개 선택자)과 선택자별로 대조해 같은 규칙으로 적용했다.

**ⓑ 그대로 (고정 안내 주석, 17개 선택자)**: `.brand em`(9px), `.nav-title`(9px), `.nav-soon`(8px), `.kicker`(9px), `.card-head p`(10px), `.small`(10px), `.coach p`(10px), `.modal p`(10px), `.modal ul`(11px), `.goal-switch small`(9px), `.scope-note`(10px), `.eyebrow`(9px), `.pw-rules`(10px), `.block-small`(9px), `.scope-label`(9px), `.level-desc summary`(9px), `.soon-note`(9px).
- 지시서 목록 14개 + 개발팀 분류 3개: `.nav-soon`(8px, "준비 중" 표시: 매번 같은 문구), `.pw-rules`(10px, 암호 규칙 안내: 매번 같은 문구), `.modal ul`(11px, 동의 모달 안내 목록: 처음 한 번 읽는 고정 문구).
- 모두 목업에서도 크기가 바뀌지 않은 선택자다.

**ⓐ 키움 (동적·조작 글, 76개 선택자)**:

| 변경 | 선택자 |
|---|---|
| 8→10px (14) | `.day`, `.record-select small`, `.record-delete`, `.insight-copy > small`, `.timer-label`, `.timer-status`, `.mode-pill`, `.mini-bars span i`, `.mini-days`, `.nav-item`, `.conversation-item span`, `.bubble small`, `.wbs-date`, `.insight-label` |
| 9→11px (17) | `.pill`, `.stat small`, `.stat strong small`, `.bar-label`, `.task-info small`, `.task-time`, `.chip`, `.resource p`, `.resource a`, `.task-record-meta`, `.record-select strong`, `.timer-actions .btn`, `.context-block .small`, `.wbs-row p`, `.weekday-select`, `th`, `.resource-url` |
| 10→12px (28) | `.user-mini small`, `.today-date`, `.btn.small`, `.link-btn`, `.stat label`, `.progress-top p`, `.task-info strong`, `.coach .btn`, `.field label`, `.tab`, `.resource strong`, `.search-links a`, `.searchbar`, `.insight-copy > p`, `.goal-switch label`, `.save-status`, `.inline-confirm`, `.task-no`, `.task-remove`, `.conversation-item strong`, `.context-block p`, `.bubble`, `.composer input`, `.wbs-row strong`, `th, td`, `.admin-banner`, `.insight-copy .insight-part p`, `.resource-desc` |
| 11→12px (17) | `.user-mini strong`, `.crumb`, `.search`, `.btn`, `.task-check`, `.field input, .field select, .field textarea`, `.goal-switch select`, `.goal-switch strong`, `.error`, `ul`, `.consent-check`, `.task-edit-row input, .task-edit-row textarea, .task-edit-row select`, `.combo-toggle`, `.combo-option`, `.advice-title`, `.plan-week-heading`, `.mode-banner` |

**개발팀이 분류한 선택자 (목업 변경 목록에 같은 이름이 없는 것, 19개)**: 원칙(데이터·상태·조작 = ⓐ)으로 올렸다. PM 확인 요청.
| 선택자 | 크기 | 이유 |
|---|---|---|
| `.stat strong small` | 9→11 | 통계 큰 숫자 옆 단위(숫자와 같이 바뀜). 목업의 `.stat small` 과 같은 취급 |
| `.search-links a` | 10→12 | 누르는 링크 |
| `.goal-switch strong` | 11→12 | 현재 학습 이름(데이터) |
| `.error` | 11→12 | 오류 문구(사건별) |
| `ul`(기본) | 11→12 | 학습 계획 저장 화면의 과제 목록(데이터). 동의 모달의 목록은 `.modal ul`(ⓑ, 11px) 이 이긴다 |
| `.consent-check` | 11→12 | 체크 상자 라벨(조작) |
| `.inline-confirm` | 10→12 | "정말 삭제할까요?" 확인(조작) |
| `.task-edit-row input/textarea/select` | 11→12 | 입력(목업 `.field input` 과 같은 취급) |
| `.combo-toggle`, `.combo-option` | 11→12 | 수준 콤보(조작·데이터) |
| `.task-no`, `.task-remove` | 10→12 | 과제 번호·삭제 링크(조작) |
| `.advice-title` | 11→12 | AI 조언 제목(생성 결과) |
| `.insight-label` | 8→10 | 인사이트 라벨 |
| `.insight-copy .insight-part p` | 10→12 | 인사이트 본문(목업 `.insight-copy>p` 와 같은 취급) |
| `.plan-week-heading`, `.mode-banner` | 11→12 | 주차 제목, 모드 띠(상태) |
| `.resource-url`, `.resource-desc` | 9→11, 10→12 | 참고자료 데이터 |

**`.small` 분리**: 하지 않았다(ⓑ 10px 유지). "아직 기록이 없습니다" 같은 상태 문구도 10px 로 남는다. 올려야 보기 좋다고 판단되면 별도 CR 로 분리를 제안한다.

**`.nav-item`**: 데스크톱은 이미 12px, 모바일 하단 메뉴(8px)만 10px(목업과 같음). `.goal-switch label` 은 10→12 + `nowrap`.

## 3. 화면 확인 (dev 모드, Chrome 헤드리스, 폭 1440·900·390)
화면 11개 × 3폭 = **33건**: 동의 모달(첫 화면), 대시보드, 학습 경로, 과제 계획, 실행 기록, 종합 분석, AI 튜터, 설정, 관리자 3개(사용자 관리, 참고자료 관리, 사용자 피드백. 관리자 계정은 dev 모드 `ADMIN_UIDS` 로 만듦). 같은 페이지에서 새 CSS 와 이전 CSS(커밋된 `globals.css`)를 번갈아 적용해 측정하고 전·후를 비교했다.
- ① 가로 스크롤: 새로 생긴 것 **0건**(33건 모두 없음).
- ② 글자 잘림·겹침: 새로 생긴 잘림 **0건**.
- ③ 8자 이하 짧은 라벨이 쪼개진 것: 새로 생긴 것 **0건**(`현재 학습` 포함).
- ④ 고정 폭: `.searchbar`(220px 폭 글자 47px/여유 123px 이상), `.weekday-select`(92px, 글자 45px/여유 62px), 모바일 하단 메뉴(66~75px, 잘림 없음, 높이 48px) 모두 문제 없음. 관리자·분석 화면 포함 페이지 오류 0건.
- ⑤ 줄바꿈이 늘어난 것: 대시보드 390px 2곳, 실행 기록 390px 1곳, 관리자 사용자 390px 1곳(총 4곳, 1440·900px 은 0곳). PM 목업 시험(24곳)보다 적다. 측정 방식이 달라(내 측정은 글자만 있는 가장 안쪽 요소 단위, 같은 이름의 요소는 하나로 합침, 데이터는 샘플 1개) 직접 비교는 어렵지만 "더 크게 달라진" 경우는 없다.
- 문제가 나와 값을 되돌리거나 폭을 고친 곳은 없다.

## 4. 목업 대조
| 화면 | 폭 | 목업과 일치 | 다른 점 |
|---|---|---|---|
| 동의 모달 | 1440/900/390 | 일치(모달 안내 `.modal p`·`.modal ul` 그대로, 체크 라벨·버튼 12px) | — |
| 대시보드 | 1440/900/390 | 일치(통계·과제·막대 라벨 등 목업 변경 선택자와 같은 값) | 390px 에서 2곳 줄바꿈 증가(허용) |
| 학습 경로 | 1440/900/390 | 일치 | 목업에 없는 선택자(콤보, 과제 편집 입력) 는 위 개발팀 분류표 |
| 과제 계획 | 1440/900/390 | 일치 | `.weekday-select`·`.wbs-date` 목업과 같음 |
| 실행 기록 | 1440/900/390 | 일치 | 390px 에서 1곳 줄바꿈 증가 |
| 종합 분석 | 1440/900/390 | 일치 | — |
| AI 튜터 | 1440/900/390 | 일치(말풍선 12px, 시각 10px) | 실제 AI 대화 데이터 없이 빈 상태로 확인 |
| 설정 | 1440/900/390 | 일치 | — |
| 관리자(사용자·참고자료·피드백) | 1440/900/390 | 일치(`th` 11px, `td` 12px) | 390px 사용자 관리 1곳 줄바꿈 증가 |
선택자 단위 대조: 목업에서 크기가 바뀐 선택자 중 구현에 있는 것은 모두 같은 값으로 바뀌었고, 목업에서 안 바뀐 ⓑ 선택자는 모두 그대로다(자동 대조). 목업에만 있는 선택자(`.level`, `.level-pick`, `.role-switch`, `.session-*`, `.toast`)는 구현에 같은 규칙이 없어 해당 없음.

## 5. 시험
**npm test 246건 통과(기준 246, 시험 추가·변경 없음), `npm run typecheck`, `npm run build` 통과.** 백엔드 변경 없음(pytest 미실행).

## 6. 미검증·참고
- 헤드리스 측정이라 글자 모양·간격의 "보기 좋음"은 사람이 봐야 한다. 특히 실행 기록·튜터·대시보드를 390px 로 직접 확인하길 권한다.
- AI 튜터는 대화·AI 응답 데이터가 있는 상태, 인사이트 카드의 생성 결과, 학습 경로의 긴 계획 미리보기는 실제 데이터로 확인하지 못했다(빈 상태 또는 샘플 데이터).
- 관리자 화면은 샘플 없이(표가 비어 있거나 소수 행) 확인했다. 표 데이터가 많을 때의 `th/td` 12px 줄바꿈은 미확인.
- 누르는 영역(터치 높이) 점검은 하지 않았다(글자 크기 외 변경 없음).
- 글자 색 진하게 하기(설계 §6-2)는 지시서에 없어 하지 않았다.
- 확인용 `npm run build` 는 포트 3000 개발 서버와 `.next` 를 공유한다. 화면이 이상하면 그 서버를 다시 시작.
- 이 작업과 무관한 파일은 커밋하지 않았다: `docs/프롬프트와 응답사례연구.md`, `frontend/AGENTS.md`, `변경관리내역서.hwp/.pdf`.
