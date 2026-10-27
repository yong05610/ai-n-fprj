/**
 * PaceMate 사용자 테스트 설문을 Google Forms 로 만드는 Apps Script.
 * 문항 원본: docs/user_test_survey.md (2026-10-27, 암호 로그인 포함판)
 *
 * 사용법
 * 1. https://script.google.com 에서 [새 프로젝트]를 만든다.
 * 2. 기본 코드를 모두 지우고 이 파일 내용을 붙여 넣은 뒤 저장한다.
 * 3. 위쪽 함수 선택에서 createPaceMateSurvey 를 고르고 [실행]을 누른다.
 *    처음 한 번은 권한 허용 창이 뜬다(내 Google Drive 에 설문을 만드는 권한).
 * 4. [실행 로그]에 나온 "응답 링크"를 테스터에게, "편집 링크"는 본인만 쓴다.
 * 같은 함수를 다시 실행하면 설문이 하나 더 만들어진다(기존 설문은 바뀌지 않는다).
 */
function createPaceMateSurvey() {
  var SCALE_LOW = '전혀 그렇지 않다';
  var SCALE_HIGH = '매우 그렇다';

  var form = FormApp.create('PaceMate 사용자 테스트 설문');
  form.setDescription(
    'PaceMate 를 사용해 주셔서 감사합니다. 5~7분 정도 걸립니다.\n' +
    '응답은 익명으로 수집되며 서비스 개선에만 사용합니다. 이름·이메일 등은 받지 않습니다.\n' +
    '테스트에서 만든 학습 데이터는 PaceMate [내 정보·설정] → 데이터 삭제로 직접 지울 수 있습니다.'
  );
  form.setCollectEmail(false);           // 이메일 수집 끄기(익명)
  form.setLimitOneResponsePerUser(false); // 켜면 Google 로그인이 필요해져 익명이 아니게 된다
  form.setAllowResponseEdits(false);
  form.setProgressBar(true);
  form.setShowLinkToRespondAgain(false);
  form.setConfirmationMessage('응답해 주셔서 감사합니다. 의견은 PaceMate 개선에 반영하겠습니다.');

  // 구역 1. 사용 환경과 진행 정도
  form.addSectionHeaderItem().setTitle('1. 사용 환경과 진행 정도');
  form.addCheckboxItem()
    .setTitle('1. PaceMate 를 어떤 기기로 사용하셨나요?')
    .setChoiceValues(['PC·노트북', '휴대폰', '태블릿'])
    .setRequired(true);
  form.addCheckboxItem()
    .setTitle('2. 아래 중 해 보신 것을 모두 골라 주세요.')
    .setChoiceValues([
      'AI 추천으로 학습 경로 만들기',
      '학습 계획 확정',
      '학습 기록 1건 이상(타이머 또는 직접 입력)',
      '한 줄 회고 쓰기',
      'AI 튜터에게 질문',
      'AI 인사이트 받기',
      '대시보드에서 오늘 할 과제 확인'
    ])
    .setRequired(true);
  form.addMultipleChoiceItem()
    .setTitle('3. 진행하다 멈추거나 막힌 단계가 있었다면 어디였나요?')
    .setChoiceValues([
      '없었음',
      '학습 경로 만들기',
      '계획 확정',
      '학습 기록',
      '회고',
      'AI 튜터',
      '화면이 안 열리거나 오래 기다림'
    ])
    .showOtherOption(true);

  // 구역 2. 만족도
  form.addPageBreakItem().setTitle('2. 만족도').setHelpText('1 = 전혀 그렇지 않다, 5 = 매우 그렇다');
  addScale(form, '4. 서비스를 쓰기 편했다.', true);
  addScale(form, '5. AI 가 만든 학습 계획이 내 목표와 시간에 맞았다.', true);
  addScale(form, '6. AI 튜터의 답변이 학습에 도움이 됐다. (튜터를 안 썼으면 건너뛰기)', false);
  addScale(form, '7. 계획 화면과 튜터에 나온 참고자료(링크·출처)가 학습에 도움이 됐다.', false);
  addScale(form, '8. AI 인사이트(학습 요약과 다음 행동 제안)가 도움이 됐다. (안 받았으면 건너뛰기)', false);

  // 구역 3. 기능별 확인
  form.addPageBreakItem().setTitle('3. 기능별 확인');
  form.addMultipleChoiceItem()
    .setTitle('9. 학습 타이머를 쓰다가 잠깐 멈추고(일시정지) 싶었던 적이 있나요?')
    .setChoiceValues(['있었다', '없었다', '타이머를 쓰지 않았다']);
  form.addMultipleChoiceItem()
    .setTitle('10. AI 가 만든 계획의 분량은 어땠나요?')
    .setChoiceValues(['너무 적었다', '적당했다', '너무 많았다', '잘 모르겠다']);
  form.addMultipleChoiceItem()
    .setTitle('11. PaceMate 를 다른 PC 나 휴대폰에서도 이어서 쓰려고 한 적이 있나요?')
    .setChoiceValues([
      '있다, 이어지지 않아 불편했다',
      '있다, 암호 로그인으로 이어서 썼다',
      '없다, 한 기기에서만 썼다'
    ])
    .setRequired(true);
  addScale(form, '12. 여러 기기에서 같은 기록으로 이어 쓰는 기능이 얼마나 필요하다고 느끼셨나요?', false);
  addScale(form, '13. (암호 로그인을 써 보신 분만) 암호 등록과 로그인은 쉬웠나요?', false);

  // 구역 4. 자유 의견
  form.addPageBreakItem().setTitle('4. 자유 의견');
  form.addParagraphTextItem().setTitle('14. 가장 불편하거나 헷갈렸던 점은 무엇인가요?');
  form.addParagraphTextItem().setTitle('15. 가장 좋았던 점은 무엇인가요?');
  form.addParagraphTextItem().setTitle('16. 있었으면 하는 기능이나 바꾸고 싶은 점이 있나요?');
  form.addParagraphTextItem().setTitle('17. 그 밖에 하고 싶은 말씀');

  Logger.log('응답 링크(테스터에게 보냄): ' + form.getPublishedUrl());
  Logger.log('편집 링크(본인만 사용): ' + form.getEditUrl());

  function addScale(f, title, required) {
    f.addScaleItem()
      .setTitle(title)
      .setBounds(1, 5)
      .setLabels(SCALE_LOW, SCALE_HIGH)
      .setRequired(required);
  }
}
