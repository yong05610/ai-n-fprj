/**
 * The current screen lives in the URL hash so a refresh keeps it: "#analysis", and for the
 * tutor "#tutor/<conversation_id>". Pure helpers, no window access.
 */
export const VIEWS = ["dashboard", "path", "wbs", "execution", "analysis", "tutor", "settings", "admin-users", "admin-feedback", "admin-library"] as const;
export type View = (typeof VIEWS)[number];

/** The admin screens (hash "#admin-..."). Only the server's profile.is_admin decides who may see them. */
export function isAdminView(view: View | null): boolean {
  return view !== null && view.startsWith("admin-");
}

/** An admin screen is left (back to the dashboard) once the server says the user is not an admin. */
export function mustLeaveAdminView(isAdmin: boolean | null, view: View | null): boolean {
  return isAdmin === false && isAdminView(view);
}

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
