import assert from "node:assert/strict";
import { test } from "node:test";

import { latestExtraLinks, latestSources, parseSummaryLines, referencePanelState, shortenText, type TutorMessage } from "./tutorState";

const src = { doc_id: "doc_002", title: "자료", source_name: "공식 문서", url: "https://example.com" };
const user = (c: string): TutorMessage => ({ role: "user", content: c, timestamp: "t", sources: [] });
const bot = (c: string, sources = [] as TutorMessage["sources"]): TutorMessage => ({ role: "assistant", content: c, timestamp: "t", sources });

test("reference panel: before any answer, with sources, and without material", () => {
  assert.equal(referencePanelState([]), "ask");
  assert.equal(referencePanelState([user("q")]), "ask");
  assert.equal(referencePanelState([user("q"), bot("a", [src])]), "sources");
  assert.equal(referencePanelState([user("q"), bot("a", [])]), "none");
});

test("only the latest assistant answer decides the sources", () => {
  const messages = [user("q1"), bot("a1", [src]), user("q2"), bot("a2", [])];
  assert.deepEqual(latestSources(messages), []);
  assert.equal(referencePanelState(messages), "none");
  assert.deepEqual(latestSources([user("q1"), bot("a1", [src])]), [src]);
});

test("summary lines split into title and level text", () => {
  const lines = parseSummaryLines("Python · 기본문법 | 현재 입문 → 목표 실무 | 진행률 25% (1/4개 과제)\nJS · 비동기 | 현재 a → 목표 b | 진행률 0% (0/2개 과제)");
  assert.equal(lines.length, 2);
  assert.deepEqual(lines[0], { title: "Python · 기본문법", levels: "현재 입문 → 목표 실무" });
  assert.deepEqual(parseSummaryLines("진행 중인 학습이 없습니다."), [{ title: "진행 중인 학습이 없습니다.", levels: null }]);
  assert.deepEqual(parseSummaryLines(""), []);
});

test("shortenText collapses whitespace and cuts with an ellipsis", () => {
  assert.equal(shortenText("짧은  글\n입니다", 20), "짧은 글 입니다");
  assert.equal(shortenText("가나다라마바사", 4), "가나다라…");
});

test("latestExtraLinks reads the newest assistant answer and filters unsafe links", () => {
  const msg = (extra: Partial<TutorMessage>): TutorMessage => ({ role: "assistant", content: "a", timestamp: "t", sources: [], ...extra });
  const none = latestExtraLinks([{ role: "user", content: "q", timestamp: "t", sources: [] }]);
  assert.deepEqual(none, { related: [], search: [] });
  const old = msg({ search_links: [{ label: "x", url: "https://a.b/?q=1" }] });
  const newest = msg({
    related_links: [{ title: "자료", source_name: "MDN", url: "https://example.org/a" }],
    search_links: [
      { label: "ok", url: "https://www.google.com/search?q=a" },
      { label: "bad", url: "javascript:alert(1)" },
    ],
  });
  const got = latestExtraLinks([old, { role: "user", content: "q", timestamp: "t", sources: [] }, newest]);
  assert.equal(got.related.length, 1);
  assert.deepEqual(got.search.map((l) => l.label), ["ok"]);
  assert.deepEqual(latestExtraLinks([msg({})]), { related: [], search: [] }); // older response shape
});
