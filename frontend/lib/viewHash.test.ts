import assert from "node:assert/strict";
import { test } from "node:test";

import { buildHash, parseHash } from "./viewHash";

test("a plain view hash", () => {
  assert.deepEqual(parseHash("#analysis"), { view: "analysis", param: null });
  assert.deepEqual(parseHash("dashboard"), { view: "dashboard", param: null });
});

test("the tutor hash carries the conversation id", () => {
  assert.deepEqual(parseHash("#tutor/abc123"), { view: "tutor", param: "abc123" });
  assert.deepEqual(parseHash("#tutor"), { view: "tutor", param: null });
});

test("unknown views and malformed ids are dropped, not trusted", () => {
  assert.deepEqual(parseHash("#nope"), { view: null, param: null });
  assert.deepEqual(parseHash(""), { view: null, param: null });
  assert.deepEqual(parseHash("#tutor/../../etc"), { view: "tutor", param: null });
  assert.deepEqual(parseHash("#tutor/a b"), { view: "tutor", param: null });
  assert.deepEqual(parseHash("#nope/abc"), { view: null, param: null });
});

test("buildHash round-trips and refuses an unsafe id", () => {
  assert.equal(buildHash("tutor", "abc123"), "#tutor/abc123");
  assert.equal(buildHash("tutor"), "#tutor");
  assert.equal(buildHash("tutor", "a/b"), "#tutor");
  assert.deepEqual(parseHash(buildHash("tutor", "x_y-1")), { view: "tutor", param: "x_y-1" });
});
