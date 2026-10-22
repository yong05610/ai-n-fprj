import assert from "node:assert/strict";
import { test } from "node:test";

import { startDateError } from "./wizardDates";

const TODAY = "2026-10-21";

test("a start date of today or later with a later target is valid, on any weekday", () => {
  assert.equal(startDateError("2026-10-21", "2026-12-31", TODAY), null); // today (Wednesday)
  assert.equal(startDateError("2026-10-25", "2026-12-31", TODAY), null); // a Sunday: no Monday needed
});

test("the target date may equal the start date", () => {
  assert.equal(startDateError("2026-10-26", "2026-10-26", TODAY), null);
});

test("a past start date is rejected", () => {
  assert.match(startDateError("2026-10-20", "2026-12-31", TODAY) ?? "", /오늘 이후/);
});

test("a target date before the start date is rejected", () => {
  assert.match(startDateError("2026-10-26", "2026-10-25", TODAY) ?? "", /시작일 이후/);
});

test("an empty start date asks for one; an empty target date is not this function's concern", () => {
  assert.match(startDateError("", "2026-12-31", TODAY) ?? "", /선택/);
  assert.equal(startDateError("2026-10-21", "", TODAY), null);
});
