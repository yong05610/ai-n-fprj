import assert from "node:assert/strict";
import { test } from "node:test";

import { MAX_RELATED_LINKS, MAX_SEARCH_LINKS, sourceLine, visibleRelatedLinks, visibleSearchLinks } from "./searchLinks";

const g = { label: "구글에서 검색 (검토 전 외부 링크)", url: "https://www.google.com/search?q=%ED%8C%8C%EC%9D%B4%EC%8D%AC" };
const y = { label: "유튜브에서 검색 (검토 전 외부 링크)", url: "https://www.youtube.com/results?search_query=a" };

test("search links keep https links with a label, at most three", () => {
  assert.deepEqual(visibleSearchLinks([g, y]), [g, y]);
  assert.equal(visibleSearchLinks([g, y, g, y]).length, MAX_SEARCH_LINKS);
});

test("search links drop non-https, javascript:, malformed and unlabeled entries", () => {
  assert.deepEqual(visibleSearchLinks([{ label: "x", url: "http://a.b" }]), []);
  assert.deepEqual(visibleSearchLinks([{ label: "x", url: "javascript:alert(1)" }]), []);
  assert.deepEqual(visibleSearchLinks([{ label: "x", url: "not a url" }]), []);
  assert.deepEqual(visibleSearchLinks([{ label: "  ", url: g.url }]), []);
});

test("missing or empty input gives no links", () => {
  assert.deepEqual(visibleSearchLinks(undefined), []);
  assert.deepEqual(visibleSearchLinks(null), []);
  assert.deepEqual(visibleRelatedLinks(undefined), []);
});

test("related links keep at most two reviewed https materials", () => {
  const r = (n: number) => ({ title: `자료 ${n}`, source_name: "MDN", url: `https://example.org/${n}` });
  assert.equal(visibleRelatedLinks([r(1), r(2), r(3)]).length, MAX_RELATED_LINKS);
  assert.deepEqual(visibleRelatedLinks([{ title: "x", source_name: null, url: "ftp://x" }]), []);
});

test("source line joins the non-empty parts", () => {
  assert.equal(sourceLine("MDN Web Docs", "웹 개발 / HTML"), "MDN Web Docs · 웹 개발 / HTML");
  assert.equal(sourceLine(null, "웹 개발 / HTML"), "웹 개발 / HTML");
  assert.equal(sourceLine("MDN", undefined), "MDN");
  assert.equal(sourceLine("", ""), "");
});
