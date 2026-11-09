// CR-012: the AI advice has line breaks and "- " lists, so every place that shows it keeps the line breaks.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("the advice style keeps line breaks and does not touch size or layout", () => {
  const css = read("../app/globals.css");
  const rule = css.split("\n").find((l) => l.startsWith(".advice-text"));
  assert.ok(rule && rule.includes("white-space: pre-line"));
  assert.ok(!/font-size|margin|padding|display/.test(rule.split("/*")[0]), "no size or layout change");
});

test("the plan preview and the plan screen show the advice with that style", () => {
  const wizard = read("../components/LearningPathWizard.tsx");
  assert.match(wizard, /<p className="advice-text">\{draft\.advice\.content\}<\/p>/);
  const screen = read("../components/WeeklyPlanScreen.tsx");
  assert.match(screen, /className="small muted advice-text"[^>]*>\s*\{goal\.advice_content\}/);
});

test("no other component prints the advice text without the style", () => {
  for (const file of ["Dashboard", "SettingsScreen", "ExecutionScreen", "InsightCard"]) {
    assert.ok(!/advice_content|advice\.content/.test(read(`../components/${file}.tsx`)), file);
  }
});
