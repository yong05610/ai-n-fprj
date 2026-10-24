"use client";

import { AccountIdCard } from "@/components/AccountIdCard";
import { DeleteDataSection } from "@/components/DeleteDataSection";
import { FeedbackCard } from "@/components/FeedbackCard";

/**
 * 내 정보·설정 (Phase 5C, minimal). Only what the consent notice promises is here: the data
 * deletion request. Goal editing is not part of the MVP (Phase 7 decision): a new learning path is made instead.
 */
export function SettingsScreen() {
  return (
    <>
      <div className="heading">
        <div>
          <p className="kicker">ACCOUNT &amp; PRIVACY</p>
          <h1>내 정보와 개인정보</h1>
          <p>익명 사용자 설정 및 저장 기록을 관리합니다.</p>
          <p className="small muted">학습 목표를 바꾸려면 새 학습 경로를 만드세요.</p>
        </div>
      </div>
      <div className="grid columns">
        <DeleteDataSection />
        <AccountIdCard />
      </div>
      <FeedbackCard />
    </>
  );
}
