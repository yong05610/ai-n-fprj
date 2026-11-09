/**
 * CR-012 (2nd): the current and the target level of the learning-path screen are one combo box each.
 * The box shows the level NAME; the user picks a level from the AI's list (which fixes its `order`) and may
 * then rewrite the name in the same box. The order is always the one of the LAST level picked from the list:
 * rewriting the name never changes it. The order is never shown (core decision: it is a rank, not a score).
 *
 * Pure functions only, so the rules are tested without a browser.
 */

export type LevelItem = { order: number; name: string; description: string };
export type LevelSelection = { order: number | null; name: string; description: string };

export const LEVEL_NAME_MAX = 100;
export const LEVEL_DESC_MAX = 2000;

export const EMPTY_LEVEL: LevelSelection = { order: null, name: "", description: "" };

export function selectionFrom(level: LevelItem | null | undefined): LevelSelection {
  return level ? { order: level.order, name: level.name, description: level.description } : EMPTY_LEVEL;
}

/** The user picked `order` from the list: the order, the name and the description come from that level. */
export function pickLevel(levels: LevelItem[], order: number): LevelSelection {
  return selectionFrom(levels.find((l) => l.order === order));
}

/** Rewriting the name keeps the order (and the description) of the last picked level. */
export function editName(selection: LevelSelection, name: string): LevelSelection {
  return { ...selection, name };
}

export function editDescription(selection: LevelSelection, description: string): LevelSelection {
  return { ...selection, description };
}

/** The target list shows only levels above the current one (no current level yet: all of them). */
export function targetOptions(levels: LevelItem[], currentOrder: number | null): LevelItem[] {
  return levels.filter((l) => currentOrder == null || l.order > currentOrder);
}

/**
 * After the current level changed: a target that is now the same or lower becomes the next higher level
 * (as before). A target that was never set also gets it; with no higher level the target is empty.
 * Returns the same object when nothing has to change.
 */
export function adjustTarget(levels: LevelItem[], current: LevelSelection, target: LevelSelection): LevelSelection {
  if (current.order == null) return target;
  if (target.order != null && target.order > current.order) return target;
  const next = levels.find((l) => l.order > (current.order as number));
  return selectionFrom(next);
}

/**
 * Why a level cannot be used for the plan, or null. No order = nothing was ever picked from the list (the order
 * cannot be known from typed text); an empty or too long name / description is refused like the server does.
 */
export function levelProblem(selection: LevelSelection): string | null {
  if (selection.order == null) return "목록에서 수준을 골라 주세요.";
  if (!selection.name.trim()) return "수준 이름을 입력해 주세요.";
  if (selection.name.length > LEVEL_NAME_MAX) return `수준 이름은 ${LEVEL_NAME_MAX}자 이하로 써 주세요.`;
  if (selection.description.length > LEVEL_DESC_MAX) return `수준 설명은 ${LEVEL_DESC_MAX}자 이하로 써 주세요.`;
  return null;
}

/** Keyboard moves in the open list: the index of the active option after ArrowDown / ArrowUp (-1 = none). */
export function nextActiveIndex(key: "ArrowDown" | "ArrowUp", active: number, count: number, selectedIndex: number): number {
  if (count <= 0) return -1;
  if (active < 0) return key === "ArrowDown" ? (selectedIndex >= 0 ? selectedIndex : 0) : count - 1;
  return key === "ArrowDown" ? Math.min(active + 1, count - 1) : Math.max(active - 1, 0);
}
