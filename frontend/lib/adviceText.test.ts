// CR-012: the AI advice has line breaks and "- " lists, so every place that shows it keeps the line breaks.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("the advice style keeps line breaks and does not touch margin or layout", () => {
  const css = read("../app/globals.css");
  const rule = css.split("\n").find((l) => l.startsWith(".advice-text"));
  assert.ok(rule && rule.includes("white-space: pre-line"));
  assert.ok(!/margin|padding|display/.test(rule.split("/*")[0]), "no margin or layout change");
});

test("the advice body is 12px with line height 1.6 in both places (CR-013 fix 2)", () => {
  const css = read("../app/globals.css");
  const rule = css.split("\n").find((l) => /^\.advice-text, \.coach p\.advice-text/.test(l));
  assert.ok(rule && /font-size: 12px/.test(rule) && /line-height: 1\.6/.test(rule));
  // the preview's `.coach p` (10px) must not win: the selector above is more specific
  assert.ok(/\.coach p \{ font-size: 10px/.test(css));
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
