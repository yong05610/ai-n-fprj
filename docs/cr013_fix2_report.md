# CR-013 수정 2 보고서 — 조언 본문 글자 크기 12px · 줄 간격 1.6

작성: 개발팀, 2026-11-10. 요청: `docs/cr013_verification.md` 의 "수정 2 요청". 프론트엔드 CSS 한 곳과 시험 1건만 바꿨다(백엔드·API 변경 없음).

## 1. 무엇을 고쳤나
- 조언 본문(`.advice-text`)을 **12px, 줄 간격 1.6**(설명 글 `.description` 과 같은 값)으로 했다.
- 두 곳 모두 적용: 계획 미리보기(보라색 상자, `.coach p`)와 학습 과제 계획 화면(`.small`).
- 원인 메모: 계획 미리보기의 `.coach p`(10px)는 선택자 우선순위가 `.advice-text` 보다 높아 이기므로, `.coach p.advice-text` 를 함께 적었다. 학습 과제 계획 화면은 `.small`(10px)보다 `.advice-text` 가 파일 뒤에 있어 이긴다. 그래서 마크업(`small` 클래스)은 건드리지 않았다.
- 그대로 둔 것: 조언 제목, "AI 생성 · 참고용", 미리보기의 흰 글자색(`#e8ebff`), 줄바꿈 유지(`white-space: pre-line`).

## 2. 바꾼 파일
| 파일 | 내용 |
|---|---|
| `frontend/app/globals.css` | +2줄: 설명 주석, `.advice-text, .coach p.advice-text { font-size: 12px; line-height: 1.6; }` |
| `frontend/lib/adviceText.test.ts` | 시험 1건 추가(CSS 값), 기존 시험 한 줄의 문구를 "크기 변경 없음" → "여백·배치 변경 없음"으로 조정(기대 범위에서 font-size 만 뺌, 이유: 이제 크기를 의도적으로 지정) |

## 3. 시험
**npm test 237건 통과(이전 236 + 새 1), pytest 1370건 통과(백엔드 변경 없음), `npm run typecheck`, `npm run build` 통과.**
새 시험: 규칙에 `font-size: 12px`, `line-height: 1.6` 이 있고, 더 구체적인 `.coach p.advice-text` 선택자가 있으며 `.coach p` 는 10px 로 남아 있음(그래서 선택자가 필요함).

## 4. 실제 브라우저 확인 (dev 모드, Chrome 헤드리스, 6개 항목 통과)
너비 1280px 과 360px 에서 실제 앱의 CSS 로 계산된 값을 읽었다.
- 학습 과제 계획 화면 마크업(`small muted advice-text`): 12px, 줄 간격 1.6, 줄바꿈 유지.
- 계획 미리보기 마크업(`.coach p.advice-text`): 12px, 줄 간격 1.6, 글자색 `rgb(232,235,255)`(흰색 계열 유지), 줄바꿈 유지.
- 긴 조언(여러 줄)을 넣은 상태에서 가로 스크롤 없음(1280/1280, 360/360).

## 5. 미확인
- 위 브라우저 확인은 실제 앱 CSS 에 두 마크업을 같은 클래스로 만들어 계산값을 읽은 것이다. 실제 AI 조언이 들어간 두 화면을 눈으로 비교하지는 않았다(AI 호출 비용, dev 모드에는 조언이 없음).
- 실제 휴대폰 확인은 하지 않았다.
- 확인용으로 `frontend`에서 `npm run build`를 실행했다. 이미 떠 있던 포트 3000 개발 서버와 `.next` 폴더를 공유하므로 화면이 이상하면 그 서버를 다시 시작하면 된다.
- 작업 폴더의 이 작업과 무관한 파일은 커밋하지 않았다: `docs/프롬프트와 응답사례연구.md`, `frontend/AGENTS.md`, `변경관리내역서.hwp/.pdf`.
