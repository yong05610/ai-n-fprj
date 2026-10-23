/**
 * The current screen lives in the URL hash so a refresh keeps it: "#analysis", and for the
 * tutor "#tutor/<conversation_id>". Pure helpers, no window access.
 */
export const VIEWS = ["dashboard", "path", "wbs", "execution", "analysis", "tutor", "settings", "admin-users", "admin-feedback"] as const;
export type View = (typeof VIEWS)[number];

// Conversation ids are store-generated ids; anything else in the hash is ignored, never trusted.
const PARAM_PATTERN = /^[A-Za-z0-9_-]{1,100}$/;

export function parseHash(hash: string): { view: View | null; param: string | null } {
  const [first, second] = hash.replace(/^#/, "").split("/");
  const view = (VIEWS as readonly string[]).includes(first) ? (first as View) : null;
  const param = view && second && PARAM_PATTERN.test(second) ? second : null;
  return { view, param };
}

export function buildHash(view: View, param?: string | null): string {
  return param && PARAM_PATTERN.test(param) ? `#${view}/${param}` : `#${view}`;
}
