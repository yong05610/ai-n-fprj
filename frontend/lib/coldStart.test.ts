import assert from "node:assert/strict";
import test from "node:test";

import {
  ATTEMPT_TIMEOUT_MS,
  FAILED_MESSAGE,
  MAX_WAIT_MS,
  PREPARING_MESSAGE,
  SLOW_NOTICE_MS,
  attemptTimeoutMs,
  coldStartView,
  nextAttemptDelayMs,
  retryDelayMs,
} from "./coldStart";

test("under 8 seconds nothing is announced", () => {
  assert.equal(coldStartView(0, false), "loading");
  assert.equal(coldStartView(SLOW_NOTICE_MS - 1, false), "loading");
});

test("from 8 up to 90 seconds the notice is shown", () => {
  assert.equal(coldStartView(SLOW_NOTICE_MS, false), "preparing");
  assert.equal(coldStartView(60_000, false), "preparing");
  assert.equal(coldStartView(MAX_WAIT_MS, false), "preparing");
});

test("after 90 seconds the connection is reported as failed", () => {
  assert.equal(coldStartView(MAX_WAIT_MS + 1, false), "failed");
  assert.equal(coldStartView(300_000, false), "failed");
});

test("an answer ends the wait at any time and the notice goes away", () => {
  for (const ms of [0, 7_999, 8_000, 45_000, 90_000]) assert.equal(coldStartView(ms, true), "ready");
});

test("retries come after 2s, 4s, 8s and then stay at 8s", () => {
  assert.deepEqual([1, 2, 3, 4, 10].map(retryDelayMs), [2_000, 4_000, 8_000, 8_000, 8_000]);
  assert.equal(retryDelayMs(0), 2_000);
});

test("the last try is cut to the 90 second mark and nothing starts after it", () => {
  assert.equal(nextAttemptDelayMs(1, 1_000), 2_000);
  assert.equal(nextAttemptDelayMs(5, 70_000), 8_000);
  assert.equal(nextAttemptDelayMs(5, 86_000), 4_000);
  assert.equal(nextAttemptDelayMs(5, 89_500), 500);
  assert.equal(nextAttemptDelayMs(5, 90_000), null);
  assert.equal(nextAttemptDelayMs(5, 95_000), null);
});

test("one try never runs past the 90 seconds and never longer than its own limit", () => {
  assert.equal(attemptTimeoutMs(0), ATTEMPT_TIMEOUT_MS);
  assert.equal(attemptTimeoutMs(80_000), 10_000);
  assert.equal(attemptTimeoutMs(MAX_WAIT_MS), 1_000);
});

test("messages are the ones the plan names", () => {
  assert.equal(PREPARING_MESSAGE, "서버를 준비하고 있습니다. 잠시만 기다려 주세요.");
  assert.equal(FAILED_MESSAGE, "서버에 연결하지 못했어요.");
});
