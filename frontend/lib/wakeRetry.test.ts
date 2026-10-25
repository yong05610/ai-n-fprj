import assert from "node:assert/strict";
import test from "node:test";

import { isWakeFailure } from "./coldStart";
import { type WakeDeps, retryWhileWaking } from "./wakeRetry";
import { learningListView } from "./weekPlan";

class WakeError extends Error {}
const isWake = (e: unknown) => e instanceof WakeError;

/** A fake clock: sleeping advances time, timers fire when the clock passes them. */
function fakeDeps() {
  let t = 0;
  const timers: { at: number; fn: () => void; live: boolean }[] = [];
  const events: string[] = [];
  const fire = () => timers.filter((x) => x.live && x.at <= t).forEach((x) => ((x.live = false), x.fn()));
  const deps: WakeDeps = {
    now: () => t,
    sleep: async (ms) => {
      events.push(`sleep ${ms}`);
      t += ms;
      fire();
    },
    after: (ms, fn) => {
      const x = { at: t + ms, fn, live: true };
      timers.push(x);
      return () => (x.live = false);
    },
    onWaiting: (w) => events.push(`waiting ${w}`),
  };
  return { deps, events, advance: (ms: number) => ((t += ms), fire()), time: () => t };
}

test("a first-try success shows no notice", async () => {
  const f = fakeDeps();
  assert.equal(await retryWhileWaking(async () => "ok", isWake, f.deps), "ok");
  assert.deepEqual(f.events, []);
});

test("failures then success: notice on at the first failure, retries at 2s and 4s, notice off at the end", async () => {
  const f = fakeDeps();
  let n = 0;
  const result = await retryWhileWaking(
    async () => {
      if (++n <= 2) throw new WakeError("down");
      return "data";
    },
    isWake,
    f.deps,
  );
  assert.equal(result, "data");
  assert.deepEqual(f.events, ["waiting true", "sleep 2000", "sleep 4000", "waiting false"]);
});

test("a request that stays open for 8 seconds turns the notice on and answering turns it off", async () => {
  const f = fakeDeps();
  const result = await retryWhileWaking(
    async () => {
      f.advance(9_000);
      return "late";
    },
    isWake,
    f.deps,
  );
  assert.equal(result, "late");
  assert.deepEqual(f.events, ["waiting true", "waiting false"]);
});

test("a fast answer under 8 seconds never shows the notice", async () => {
  const f = fakeDeps();
  await retryWhileWaking(async () => (f.advance(7_000), "x"), isWake, f.deps);
  assert.deepEqual(f.events, []);
});

test("after 90 seconds the last wake-up failure is thrown, so the screen can show an error", async () => {
  const f = fakeDeps();
  await assert.rejects(
    retryWhileWaking(async () => (f.advance(15_000), Promise.reject(new WakeError("down"))), isWake, f.deps),
    WakeError,
  );
  assert.ok(f.time() >= 90_000 && f.time() <= 120_000, `ended at ${f.time()}ms`);
  assert.equal(f.events[f.events.length - 1], "waiting false");
});

test("a real answer error (not a wake-up failure) is thrown at once without retry or notice", async () => {
  const f = fakeDeps();
  let n = 0;
  await assert.rejects(
    retryWhileWaking(async () => (n++, Promise.reject(new Error("403"))), isWake, f.deps),
    /403/,
  );
  assert.equal(n, 1);
  assert.deepEqual(f.events, []);
});

test("which failures count as a waking server", () => {
  assert.equal(isWakeFailure(0, "NETWORK_ERROR"), true);
  assert.equal(isWakeFailure(0, "REQUEST_TIMEOUT"), true);
  for (const s of [502, 503, 504]) assert.equal(isWakeFailure(s, "INTERNAL_ERROR"), true);
  assert.equal(isWakeFailure(0, "CONFIG_ERROR"), false);
  for (const s of [400, 401, 403, 404, 409, 500]) assert.equal(isWakeFailure(s, "X"), false);
});

test("an unread list of learnings is an error, never the empty state", () => {
  assert.equal(learningListView(false, false, 0), "loading");
  assert.equal(learningListView(true, true, 0), "error");
  assert.equal(learningListView(true, true, 3), "error");
  assert.equal(learningListView(true, false, 0), "none");
  assert.equal(learningListView(true, false, 2), "some");
});
