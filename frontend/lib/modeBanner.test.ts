import assert from "node:assert/strict";
import { test } from "node:test";

import { type HealthState, modeBannerLines, parseHealth } from "./modeBanner";

const ok = (auth_mode: string, store_backend: string): HealthState => ({ status: "ok", modes: { auth_mode, store_backend } });

test("memory storage shows the data-loss band with the mode names", () => {
  assert.deepEqual(modeBannerLines(ok("dev", "memory"), false), ["개발 모드예요. 서버를 끄면 데이터가 사라져요. (dev / memory)"]);
  // memory with Firebase auth still loses its data
  assert.deepEqual(modeBannerLines(ok("firebase", "memory"), false), ["개발 모드예요. 서버를 끄면 데이터가 사라져요. (firebase / memory)"]);
});

test("dev auth with a persistent store says so without claiming data loss", () => {
  const lines = modeBannerLines(ok("dev", "firestore"), false);
  assert.equal(lines.length, 1);
  assert.ok(lines[0].includes("개발용 인증") && lines[0].includes("(dev / firestore)") && !lines[0].includes("사라져요"));
});

test("a Firebase / Firestore server with a Firebase frontend shows nothing", () => {
  assert.deepEqual(modeBannerLines(ok("firebase", "firestore"), false), []);
});

test("loading and a failed /health show nothing from the server (the existing error handling covers failures)", () => {
  assert.deepEqual(modeBannerLines({ status: "loading" }, false), []);
  assert.deepEqual(modeBannerLines({ status: "failed" }, false), []);
});

test("a dev frontend is always announced, whatever the server says", () => {
  assert.deepEqual(modeBannerLines({ status: "failed" }, true), ["프론트가 dev 인증 모드예요."]);
  assert.deepEqual(modeBannerLines({ status: "loading" }, true), ["프론트가 dev 인증 모드예요."]);
  assert.deepEqual(modeBannerLines(ok("dev", "memory"), true), [
    "개발 모드예요. 서버를 끄면 데이터가 사라져요. (dev / memory)",
    "프론트가 dev 인증 모드예요.",
  ]);
});

test("frontend dev with a Firebase server points out the mismatch", () => {
  assert.deepEqual(modeBannerLines(ok("firebase", "firestore"), true), [
    "프론트가 dev 인증 모드예요. 서버 인증은 firebase 예요. 서로 맞는지 확인해 주세요.",
  ]);
});

test("parseHealth accepts the server body and refuses anything else", () => {
  assert.deepEqual(parseHealth({ status: "ok", service: "pacemate-api", auth_mode: "dev", store_backend: "memory" }), { auth_mode: "dev", store_backend: "memory" });
  assert.equal(parseHealth(null), null);
  assert.equal(parseHealth("ok"), null);
  assert.equal(parseHealth({ status: "ok" }), null);
  assert.equal(parseHealth({ auth_mode: 1, store_backend: "memory" }), null);
  // an old server without the fields, or odd text, never reaches the screen
  assert.equal(parseHealth({ auth_mode: "<b>dev</b>", store_backend: "memory" }), null);
  assert.equal(parseHealth({ auth_mode: "dev", store_backend: "mem ory" }), null);
});
