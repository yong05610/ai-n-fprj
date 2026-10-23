import assert from "node:assert/strict";
import { test } from "node:test";

import {
  cooldownSeconds,
  cooldownText,
  createButtonLabel,
  footerText,
  hasDifficulty,
  nextRequestId,
  staleNotice,
} from "./insightState";

test("button label: create first, refresh afterwards, busy while running", () => {
  assert.equal(createButtonLabel(false, false), "인사이트 만들기");
  assert.equal(createButtonLabel(true, false), "인사이트 갱신");
  assert.equal(createButtonLabel(false, true), "만드는 중…");
  assert.equal(createButtonLabel(true, true), "만드는 중…");
});

test("stale notice only for a stale insight", () => {
  assert.equal(staleNotice(null), null);
  assert.equal(staleNotice({ is_stale: false }), null);
  assert.equal(staleNotice({ is_stale: true }), "기록이 바뀌었어요. 다시 만들 수 있어요.");
});

test("footer carries the AI notice and the Seoul generation time", () => {
  assert.equal(footerText(null), "내 실행 기록과 회고 기반 · AI 생성 안내");
  assert.equal(footerText("2026-10-22T05:05:00Z"), "내 실행 기록과 회고 기반 · AI 생성 안내 · 생성 10/22 14:05");
  assert.equal(footerText("2026-10-21T15:30:00Z"), "내 실행 기록과 회고 기반 · AI 생성 안내 · 생성 10/22 00:30");
});

test("the difficulty line is hidden when blank", () => {
  assert.equal(hasDifficulty({ difficulty: "" }), false);
  assert.equal(hasDifficulty({ difficulty: "   " }), false);
  assert.equal(hasDifficulty({ difficulty: "딕셔너리가 어려웠어요." }), true);
});

test("a retry reuses the key, a fresh press gets a new one", () => {
  let n = 0;
  const make = () => `id-${++n}`;
  const first = nextRequestId(null, make);
  assert.equal(nextRequestId(first, make), first);
  assert.equal(nextRequestId(null, make), "id-2");
});

test("cooldown details and text", () => {
  assert.equal(cooldownSeconds({ retry_after_seconds: 42 }), 42);
  assert.equal(cooldownSeconds({ retry_after_seconds: 41.2 }), 42);
  assert.equal(cooldownSeconds({}), null);
  assert.equal(cooldownSeconds(null), null);
  assert.equal(cooldownSeconds({ retry_after_seconds: "x" }), null);
  assert.equal(cooldownText(42), "인사이트는 42초 뒤에 다시 만들 수 있어요.");
  assert.equal(cooldownText(null), "잠시 뒤에 다시 만들 수 있어요.");
});
