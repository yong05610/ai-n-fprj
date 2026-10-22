/**
 * Splits a tutor answer into plain text, `inline code` and ```fenced code``` so the screen can
 * show code readably without a Markdown library. Pure; React still escapes every piece.
 */
export type RichSegment = { kind: "text" | "inline" | "block"; text: string };

export function splitAnswer(text: string): RichSegment[] {
  const segments: RichSegment[] = [];
  const fence = /```[^\n`]*\n?([\s\S]*?)```/g;
  let last = 0;
  for (const match of text.matchAll(fence)) {
    pushInline(segments, text.slice(last, match.index));
    segments.push({ kind: "block", text: match[1].replace(/\n$/, "") });
    last = (match.index ?? 0) + match[0].length;
  }
  pushInline(segments, text.slice(last));
  return segments;
}

function pushInline(out: RichSegment[], chunk: string): void {
  if (!chunk) return;
  chunk.split(/(`[^`\n]+`)/g).forEach((part, i) => {
    if (!part) return;
    if (i % 2 === 1) out.push({ kind: "inline", text: part.slice(1, -1) });
    else out.push({ kind: "text", text: part });
  });
}
