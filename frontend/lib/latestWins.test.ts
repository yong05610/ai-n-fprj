import assert from "node:assert/strict";
import { test } from "node:test";

import { LatestWinsSaver, type SaveState } from "./latestWins";

/** A fake server whose responses the test releases by hand, so request timing is controlled. */
function makeServer() {
  const sent: { key: string; value: string }[] = [];
  const stored = new Map<string, string>();
  const waiting: { resolve: () => void; reject: (e: Error) => void; key: string; value: string }[] = [];
  const send = (key: string, value: string) =>
    new Promise<void>((resolve, reject) => {
      sent.push({ key, value });
      waiting.push({
        key,
        value,
        resolve: () => {
          stored.set(key, value);
          resolve();
        },
        reject,
      });
    });
  const tick = () => new Promise((r) => setTimeout(r, 0));
  return { sent, stored, waiting, send, tick };
}

test("rapid changes: requests for one key go out one at a time and the server ends with the last value", async () => {
  const s = makeServer();
  const states: SaveState[] = [];
  const saver = new LatestWinsSaver<string>(s.send, (st) => states.push(st));
  saver.set("t1", "mon");
  saver.set("t1", "tue");
  saver.set("t1", "wed");
  await s.tick();
  assert.deepEqual(s.sent.map((x) => x.value), ["mon"]); // one in flight, the rest only remembered
  s.waiting[0].resolve();
  await s.tick();
  assert.deepEqual(s.sent.map((x) => x.value), ["mon", "wed"]); // "tue" was skipped, the last value follows
  s.waiting[1].resolve();
  await s.tick();
  assert.equal(s.stored.get("t1"), "wed");
  assert.equal(saver.state().status, "saved");
  assert.equal(states.some((x) => x.status === "saving"), true);
});

test("a value chosen while the last request is finishing is still sent", async () => {
  const s = makeServer();
  const saver = new LatestWinsSaver<string>(s.send, () => {});
  saver.set("t1", "mon");
  await s.tick();
  s.waiting[0].resolve();
  saver.set("t1", "fri"); // arrives right as the first request completes
  await s.tick();
  await s.tick();
  if (s.waiting[1]) s.waiting[1].resolve();
  await s.tick();
  assert.equal(s.stored.get("t1"), "fri");
});

test("changing back to an earlier value while a request is in flight still ends on the last choice", async () => {
  const s = makeServer();
  const saver = new LatestWinsSaver<string>(s.send, () => {});
  saver.set("t1", "mon");
  saver.set("t1", "tue");
  saver.set("t1", "mon");
  await s.tick();
  s.waiting[0].resolve(); // the first request (mon) completes; the latest wish is mon again
  await s.tick();
  assert.equal(s.stored.get("t1"), "mon");
  assert.equal(saver.state().status, "saved");
});

test("different keys do not block each other", async () => {
  const s = makeServer();
  const saver = new LatestWinsSaver<string>(s.send, () => {});
  saver.set("a", "mon");
  saver.set("b", "tue");
  await s.tick();
  assert.deepEqual(s.sent.map((x) => x.key).sort(), ["a", "b"]);
  s.waiting.forEach((w) => w.resolve());
  await s.tick();
  assert.equal(saver.state().status, "saved");
});

test("a failure keeps the chosen value, reports the error and retry resends the latest value", async () => {
  const s = makeServer();
  const saver = new LatestWinsSaver<string>(s.send, () => {});
  saver.set("t1", "sat");
  await s.tick();
  s.waiting[0].reject(new Error("network"));
  await s.tick();
  assert.deepEqual(saver.state(), { status: "error", failedKeys: ["t1"] });
  assert.equal(s.stored.has("t1"), false);
  saver.retry();
  await s.tick();
  assert.equal(s.sent.length, 2);
  assert.equal(s.sent[1].value, "sat"); // the same, user-chosen value (no rollback)
  s.waiting[1].resolve();
  await s.tick();
  assert.deepEqual(saver.state(), { status: "saved", failedKeys: [] });
});

test("a new choice after a failure clears that error and is sent", async () => {
  const s = makeServer();
  const saver = new LatestWinsSaver<string>(s.send, () => {});
  saver.set("t1", "mon");
  await s.tick();
  s.waiting[0].reject(new Error("x"));
  await s.tick();
  saver.set("t1", "tue");
  await s.tick();
  assert.equal(saver.state().status, "saving");
  s.waiting[1].resolve();
  await s.tick();
  assert.equal(s.stored.get("t1"), "tue");
  assert.equal(saver.state().status, "saved");
});

test("before any change the state is idle", () => {
  const saver = new LatestWinsSaver<string>(async () => {}, () => {});
  assert.deepEqual(saver.state(), { status: "idle", failedKeys: [] });
});
