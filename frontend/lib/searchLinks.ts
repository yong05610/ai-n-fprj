/**
 * Pure helpers for the server-built "직접 검색해 보기" links (Phase 6C). The server creates every
 * URL; the screen still refuses anything that is not a plain https link before rendering it.
 */
export type SearchLink = { label: string; url: string };
export type RelatedLink = { title: string; source_name: string | null; url: string };

export const SEARCH_LINKS_HEADING = "직접 검색해 보기";
export const SEARCH_LINKS_WARNING = "검토 전 외부 링크예요.";
export const RELATED_LINKS_HEADING = "함께 보면 좋은 자료";
export const MAX_SEARCH_LINKS = 3;
export const MAX_RELATED_LINKS = 2;

function isHttps(url: string): boolean {
  try {
    return new URL(url).protocol === "https:";
  } catch {
    return false;
  }
}

/** At most three https links that carry a label; anything else is dropped (never shown). */
export function visibleSearchLinks(links: SearchLink[] | null | undefined): SearchLink[] {
  return (links ?? []).filter((l) => l.label.trim() !== "" && isHttps(l.url)).slice(0, MAX_SEARCH_LINKS);
}

/** At most two reviewed link materials with a title and an https URL. */
export function visibleRelatedLinks(links: RelatedLink[] | null | undefined): RelatedLink[] {
  return (links ?? []).filter((l) => l.title.trim() !== "" && isHttps(l.url)).slice(0, MAX_RELATED_LINKS);
}

/** "{출처} · {분류}" line of a reviewed material; empty parts are skipped. */
export function sourceLine(sourceName: string | null | undefined, category?: string | null): string {
  return [sourceName, category].filter((p): p is string => !!p && p.trim() !== "").join(" · ");
}
