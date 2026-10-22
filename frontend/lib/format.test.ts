import assert from "node:assert/strict";
import { test } from "node:test";

import { formatPeriod, formatTargetMinutes, levelSummary } from "./format";

test("formatPeriod matches the mockup inside the current year", () => {
  assert.equal(formatPeriod("2026-10-05", "2026-12-28", 2026), "10/05 – 12/28");
});

test("formatPeriod adds the year to the side that is outside the current year", () => {
  assert.equal(formatPeriod("2026-10-05", "2027-01-30", 2026), "10/05 – 2027/01/30");
  assert.equal(formatPeriod("2027-02-01", "2027-03-31", 2026), "2027/02/01 – 2027/03/31");
});

test("levelSummary splits the API text and refuses anything else", () => {
  assert.deepEqual(levelSummary("입문 → 실무 기초"), { current: "입문", target: "실무 기초" });
  assert.equal(levelSummary("입문"), null);
  assert.equal(levelSummary("a → b → c"), null);
  assert.equal(levelSummary(""), null);
});

test("formatTargetMinutes shows hours only for whole hours", () => {
  assert.equal(formatTargetMinutes(420), "7시간");
  assert.equal(formatTargetMinutes(450), "450분");
  assert.equal(formatTargetMinutes(0), "0분");
});
