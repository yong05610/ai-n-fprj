import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CHOOSABLE_STATUSES,
  FEEDBACK_STATUS_LABEL,
  commentOrPlaceholder,
  consentLabel,
  feedbackScreenLabel,
  formatAverage,
  pageCount,
  requestIdFor,
} from "./adminLabels";

test("consent label covers current, older and missing consent", () => {
  assert.equal(consentLabel(true, "v1.1"), "동의함 (v1.1)");
  assert.equal(consentLabel(false, "v1.0"), "재동의 필요 (v1.0)");
  assert.equal(consentLabel(false, null), "동의 안 함");
});

test("averages show one decimal or a dash", () => {
  assert.equal(formatAverage(4.2), "4.2");
  assert.equal(formatAverage(4), "4.0");
  assert.equal(formatAverage(null), "–");
});

test("a blank comment reads as no comment", () => {
  assert.equal(commentOrPlaceholder(""), "(의견 없음)");
  assert.equal(commentOrPlaceholder("   "), "(의견 없음)");
  assert.equal(commentOrPlaceholder("좋아요"), "“좋아요”");
});

test("status labels and the choosable set (new is never choosable)", () => {
  assert.equal(FEEDBACK_STATUS_LABEL.new, "미확인");
  assert.deepEqual(CHOOSABLE_STATUSES, ["seen", "candidate", "done"]);
  assert.equal(feedbackScreenLabel("path"), "학습 경로 설정");
  assert.equal(feedbackScreenLabel("tutor"), "기타");
});

test("page count never drops below one", () => {
  assert.equal(pageCount(0, 50), 1);
  assert.equal(pageCount(50, 50), 1);
  assert.equal(pageCount(51, 50), 2);
  assert.equal(pageCount(121, 50), 3);
});

test("the idempotency key is reused for identical content and renewed when the content changes", () => {
  let n = 0;
  const make = () => `id-${++n}`;
  const first = requestIdFor(null, "a", make);
  const retry = requestIdFor(first, "a", make);
  assert.equal(retry.requestId, first.requestId);
  const edited = requestIdFor(retry, "b", make);
  assert.notEqual(edited.requestId, first.requestId);
});
