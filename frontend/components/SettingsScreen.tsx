"use client";

import { DeleteDataSection } from "@/components/DeleteDataSection";

/**
 * 내 정보·설정 (Phase 5C, minimal). Only what the consent notice promises is here: the data
 * deletion request. Profile editing and survey guidance belong to Phase 7.3.
 */
export function SettingsScreen() {
  return (
    <>
      <div className="heading">
        <div>
          <p className="kicker">ACCOUNT &amp; PRIVACY</p>
          <h1>내 정보와 개인정보</h1>
          <p>익명 사용자 설정 및 저장 기록을 관리합니다.</p>
        </div>
      </div>
      <div className="grid columns">
        <DeleteDataSection />
      </div>
    </>
  );
}
