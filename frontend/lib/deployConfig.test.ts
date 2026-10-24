import assert from "node:assert/strict";
import test from "node:test";

import { API_CONFIG_MESSAGES, apiConfigProblem, resolveApiBase } from "./deployConfig";

test("production without an API address is a setting error, not localhost", () => {
  for (const raw of [undefined, "", "   "]) {
    const base = resolveApiBase(raw, true);
    assert.equal(base, "");
    assert.equal(apiConfigProblem(base, true), "missing");
  }
  assert.match(API_CONFIG_MESSAGES.missing, /배포 설정 오류: API 주소가 없어요/);
});

test("production with an http address is a setting error", () => {
  assert.equal(apiConfigProblem(resolveApiBase("http://api.example.com", true), true), "insecure");
  assert.equal(apiConfigProblem(resolveApiBase("HTTP://api.example.com", true), true), "insecure");
});

test("production with an https address is fine, and a trailing slash is dropped", () => {
  assert.equal(resolveApiBase("https://api.example.com/", true), "https://api.example.com");
  assert.equal(apiConfigProblem("https://api.example.com", true), null);
});

test("a local http address works so a production build can be tried against a local server", () => {
  for (const url of ["http://localhost:8123", "http://127.0.0.1:8001", "http://localhost"]) {
    assert.equal(apiConfigProblem(url, true), null);
  }
  assert.equal(apiConfigProblem("http://localhost.evil.com", true), "insecure");
});

test("development keeps the old default and never reports a problem", () => {
  assert.equal(resolveApiBase(undefined, false), "http://localhost:8001");
  assert.equal(resolveApiBase("", false), "http://localhost:8001");
  assert.equal(resolveApiBase("http://localhost:9000", false), "http://localhost:9000");
  assert.equal(apiConfigProblem("", false), null);
  assert.equal(apiConfigProblem("http://api.example.com", false), null);
});
