"use client";

import { useState } from "react";

import { TERMS_VERSION } from "@/lib/consent";

type Props = {
  busy: boolean;
  errorMessage: string | null;
  onAccept: () => void;
  onDecline: () => void;
};

export function ConsentModal({ busy, errorMessage, onAccept, onDecline }: Props) {
  const [checked, setChecked] = useState(false);

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="consent-title">
      <section className="modal">
        <p className="eyebrow">WELCOME TO PACEMATE</p>
        <h2 id="consent-title">PaceMate 학습 서비스 이용 안내</h2>
        <p>서비스를 시작하기 전, 아래 내용을 확인해 주세요.</p>

        <h3>수집하는 정보</h3>
        <ul>
          <li>이름·이메일 등 개인 식별 정보는 수집하지 않습니다.</li>
          <li>학습 목표, 학습 기록, 회고, AI 튜터 대화 이력이 저장됩니다.</li>
          <li>
            모든 데이터는 <strong>익명 UID</strong>와 연결되며, 본인 외에 열람할 수 없습니다.
          </li>
        </ul>

        <h3>AI 활용</h3>
        <ul>
          <li>AI가 학습 계획, 수준 제안, 튜터 답변을 생성합니다.</li>
          <li>AI 답변은 참고용이며 정확성을 직접 확인해 주세요.</li>
          <li>학습 기록과 회고가 AI 튜터의 개인화 답변에 활용됩니다.</li>
        </ul>

        <h3>데이터 삭제</h3>
        <ul>
          <li>[내 정보·설정] 메뉴에서 언제든지 모든 학습 데이터 삭제를 요청할 수 있습니다.</li>
          <li>삭제 요청 시 학습 목표·기록·회고·대화 이력이 모두 삭제됩니다.</li>
          <li>이 서비스는 베타 테스트 중이며, 테스트 종료 후 데이터 삭제 절차를 안내드립니다.</li>
          <li>테스트 피드백을 제출하면 사용자 정보 없이 저장되어, 이후 삭제 요청으로 지울 수 없습니다. 피드백 제출은 선택입니다.</li>
        </ul>

        <label className="consent-check">
          <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} disabled={busy} />
          위 개인정보·AI 이용 안내를 읽었으며, 동의 후 익명 UID 생성과 학습 데이터 처리를 시작하는 데 동의합니다.
        </label>
        <p className="small">안내 버전 {TERMS_VERSION}</p>

        {errorMessage && (
          <p className="error" role="alert">
            {errorMessage}
          </p>
        )}

        <div className="modal-actions">
          <button className="btn secondary" onClick={onDecline} disabled={busy}>
            동의하지 않음
          </button>
          <button className="btn" onClick={onAccept} disabled={!checked || busy}>
            {busy ? "시작하는 중…" : errorMessage ? "다시 시도" : "동의하고 시작하기"}
          </button>
        </div>
      </section>
    </div>
  );
}
