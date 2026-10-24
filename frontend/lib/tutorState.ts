/** Pure state helpers for the tutor screen (Phase 6), so they can be unit-tested. */

import { type RelatedLink, type SearchLink, visibleRelatedLinks, visibleSearchLinks } from "./searchLinks";

export type TutorSource = { doc_id: string; title: string; source_name: string; url: string | null };
export type TutorMessage = {
  role: string;
  content: string;
  timestamp: string;
  sources: TutorSource[];
  // Phase 6C, built by the server at response time (absent in older responses)
  search_keywords?: string[];
  search_links?: SearchLink[];
  related_links?: RelatedLink[];
};

/** Sources used by the most recent assistant answer (empty if it used none). */
export function latestSources(messages: TutorMessage[]): TutorSource[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") return messages[i].sources ?? [];
  }
  return [];
}

/** Links of the most recent assistant answer: reviewed related materials and search links. */
export function latestExtraLinks(messages: TutorMessage[]): { related: RelatedLink[]; search: SearchLink[] } {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") {
      return { related: visibleRelatedLinks(messages[i].related_links), search: visibleSearchLinks(messages[i].search_links) };
    }
  }
  return { related: [], search: [] };
}

/**
 * What the "참고자료" block shows:
 * - "ask": no answer yet in this conversation
 * - "none": the latest answer had no reviewed material behind it (say so, invent no source)
 * - "sources": list the sources
 */
export function referencePanelState(messages: TutorMessage[]): "ask" | "none" | "sources" {
  const hasAnswer = messages.some((m) => m.role === "assistant");
  if (!hasAnswer) return "ask";
  return latestSources(messages).length > 0 ? "sources" : "none";
}

/**
 * The server's learning_summary has one learning per line:
 * "분야 · 과정 | 현재 X → 목표 Y | 진행률 n% (a/b개 과제)".
 */
export function parseSummaryLines(summary: string): { title: string; levels: string | null }[] {
  return summary
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [title, levels] = line.split(" | ");
      return { title, levels: levels ?? null };
    });
}

/** Cuts a long reflection for the side panel without breaking in the middle of nothing. */
export function shortenText(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length <= max ? flat : `${flat.slice(0, max).trimEnd()}…`;
}
