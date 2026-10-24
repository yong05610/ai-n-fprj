/**
 * Whole-course schedule placement (Phase 5F), the client mirror of backend/schedule.py.
 *
 * The wizard uses it to re-place tasks instantly while the user edits minutes or deletes tasks.
 * It is only a preview: the server places the tasks again when the plan is confirmed and those
 * stored values are the real ones. Both sides read the same test vectors
 * (backend/tests/fixtures/schedule_cases.json), so they must agree.
 *
 * Model: tasks lie end to end on a timeline of minutes; week k (0 = the week of the start date) is
 * [k * weekly, (k + 1) * weekly); a task appears in every week its interval overlaps.
 * All date arithmetic goes through lib/week.ts (Asia/Seoul, no browser-local dates).
 */
import { addDaysToDateString, daysBetweenDateStrings, mondayOfDateString } from "@/lib/week";

export type Weekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export const WEEKDAYS: Weekday[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

export type Placement = { timeline_start_minutes: number; start_week_index: number; suggested_weekday: Weekday };

/** Weeks (Monday-based, both ends included) from the week of `start` to the week of `target`; at least 1. */
export function weekCount(start: string, target: string): number {
  const weeks = daysBetweenDateStrings(mondayOfDateString(start), mondayOfDateString(target)) / 7 + 1;
  return Math.max(1, Math.round(weeks));
}

/** Days of the period, both ends included (start == target is one day). */
export function periodDays(start: string, target: string): number {
  return daysBetweenDateStrings(start, target) + 1;
}

/** The period in weeks by its real days, one decimal (61 days -> 8.7). */
export function periodWeeks(start: string, target: string): number {
  return Math.round((periodDays(start, target) / 7) * 10) / 10;
}

/**
 * Time budget of a period: floor(weekly minutes x included days / 7), never above the whole-week
 * figure (weekly minutes x weekCount). A Sunday start therefore does not count its first week whole.
 * Same rule as backend/schedule.py; both read the "available" vectors of schedule_cases.json.
 */
export function availableMinutes(weeklyHours: number, start: string, target: string): number {
  const weekly = weeklyHours * 60;
  const byDays = Math.floor((weekly * periodDays(start, target)) / 7);
  return Math.min(byDays, weekly * weekCount(start, target));
}

/** Share of the available time a plan uses, in whole percent (0 without time). */
export function coveragePercent(totalMinutes: number, available: number): number {
  return available > 0 ? Math.round((totalMinutes * 100) / available) : 0;
}

/** Days the first week has from the start date on (7 when the start is a Monday). */
export function firstWeekDays(start: string): number {
  return 7 - daysBetweenDateStrings(mondayOfDateString(start), start);
}

/** Days of the last week up to the target date (7 when the target is a Sunday). */
export function lastWeekDays(target: string): number {
  return daysBetweenDateStrings(mondayOfDateString(target), target) + 1;
}

/** floor((start % week) / week * 7) as an integer computation, so no float rounding can move a boundary. */
export function defaultWeekday(timelineStart: number, weeklyMinutes: number): Weekday {
  const offset = timelineStart % weeklyMinutes;
  return WEEKDAYS[Math.floor((offset * 7) / weeklyMinutes)];
}

function safeMinutes(value: number): number {
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
}

/** One placement per task in the given order (an empty or invalid minutes value counts as 0). */
export function placeTasks(minutesInOrder: number[], weeklyMinutes: number): Placement[] {
  let cursor = 0;
  return minutesInOrder.map((raw) => {
    const placement: Placement = {
      timeline_start_minutes: cursor,
      start_week_index: Math.floor(cursor / weeklyMinutes),
      suggested_weekday: defaultWeekday(cursor, weeklyMinutes),
    };
    cursor += safeMinutes(raw);
    return placement;
  });
}

/** Scheduled minutes of one task per week index (overlap of its interval with each week). */
export function weekPortions(timelineStart: number, minutes: number, weeklyMinutes: number): Map<number, number> {
  const portions = new Map<number, number>();
  const end = timelineStart + safeMinutes(minutes);
  for (let week = Math.floor(timelineStart / weeklyMinutes); week * weeklyMinutes < end; week++) {
    const lo = Math.max(timelineStart, week * weeklyMinutes);
    const hi = Math.min(end, (week + 1) * weeklyMinutes);
    if (hi > lo) portions.set(week, hi - lo);
  }
  return portions;
}

export type WeekItem = {
  taskIndex: number;
  /** this task's minutes inside this week */
  weekMinutes: number;
  /** false = the task started in an earlier week and continues here */
  startsHere: boolean;
  totalMinutes: number;
  /** number of weeks the task touches (1 = fits inside its start week) */
  weeksSpanned: number;
};

export type WeekGroup = {
  index: number;
  weekStart: string;
  weekEnd: string;
  /** sum of the items' minutes in this week (never above the weekly minutes) */
  scheduledMinutes: number;
  items: WeekItem[];
};

/**
 * Tasks grouped by week for the preview. Only weeks that hold something are returned, oldest first.
 * A task with 0 minutes is listed in its start week so it stays editable.
 */
export function groupByWeek(minutesInOrder: number[], weeklyMinutes: number, firstWeekMonday: string): WeekGroup[] {
  const placements = placeTasks(minutesInOrder, weeklyMinutes);
  const groups = new Map<number, WeekGroup>();
  const group = (index: number): WeekGroup => {
    let g = groups.get(index);
    if (!g) {
      const weekStart = addDaysToDateString(firstWeekMonday, 7 * index);
      g = { index, weekStart, weekEnd: addDaysToDateString(weekStart, 6), scheduledMinutes: 0, items: [] };
      groups.set(index, g);
    }
    return g;
  };
  minutesInOrder.forEach((raw, taskIndex) => {
    const total = safeMinutes(raw);
    const start = placements[taskIndex];
    const portions = weekPortions(start.timeline_start_minutes, total, weeklyMinutes);
    if (portions.size === 0) {
      group(start.start_week_index).items.push({ taskIndex, weekMinutes: 0, startsHere: true, totalMinutes: 0, weeksSpanned: 1 });
      return;
    }
    for (const [week, minutes] of portions) {
      const g = group(week);
      g.items.push({ taskIndex, weekMinutes: minutes, startsHere: week === start.start_week_index, totalMinutes: total, weeksSpanned: portions.size });
      g.scheduledMinutes += minutes;
    }
  });
  return [...groups.values()].sort((a, b) => a.index - b.index);
}

/** Case- and whitespace-insensitive title key, the same rule as the server's duplicate check. */
export function normalizedTitle(title: string): string {
  return title.split(/\s+/).filter(Boolean).join(" ").toLowerCase();
}

/** Task indexes whose title repeats an earlier one (blank titles are not counted as duplicates). */
export function duplicateTitleIndexes(titles: string[]): number[] {
  const seen = new Set<string>();
  const duplicates: number[] = [];
  titles.forEach((title, i) => {
    const key = normalizedTitle(title);
    if (!key) return;
    if (seen.has(key)) duplicates.push(i);
    else seen.add(key);
  });
  return duplicates;
}

// ---- stored plans (weekly plan screen): the placement comes from the server (timeline_start_minutes)

export type StoredPlacement = { id: string; estimated_minutes: number; timeline_start_minutes: number; order_index: number };
export type WeekTaskEntry<T> = { task: T; weekMinutes: number; startsHere: boolean; totalMinutes: number; weeksSpanned: number };

/** Tasks that have scheduled minutes in week `weekIndex` (0 = first week), in order_index order. */
export function tasksInWeek<T extends StoredPlacement>(tasks: T[], weeklyMinutes: number, weekIndex: number): WeekTaskEntry<T>[] {
  const entries: WeekTaskEntry<T>[] = [];
  for (const task of [...tasks].sort((a, b) => a.order_index - b.order_index)) {
    const portions = weekPortions(task.timeline_start_minutes, task.estimated_minutes, weeklyMinutes);
    const minutes = portions.get(weekIndex);
    if (!minutes) continue;
    entries.push({
      task,
      weekMinutes: minutes,
      startsHere: Math.floor(task.timeline_start_minutes / weeklyMinutes) === weekIndex,
      totalMinutes: safeMinutes(task.estimated_minutes),
      weeksSpanned: portions.size,
    });
  }
  return entries;
}

/** Index of the last week that has scheduled minutes, or -1 when nothing is scheduled. */
export function lastScheduledWeekIndex(tasks: StoredPlacement[], weeklyMinutes: number): number {
  let last = -1;
  for (const t of tasks) {
    for (const week of weekPortions(t.timeline_start_minutes, t.estimated_minutes, weeklyMinutes).keys()) last = Math.max(last, week);
  }
  return last;
}

/** Mondays of every week of the plan, from the first week through `max(plan weeks, last scheduled week)`. */
export function planWeekMondays(firstWeekMonday: string, planWeeks: number, lastScheduledIndex: number): string[] {
  const count = Math.max(planWeeks, lastScheduledIndex + 1, 1);
  return Array.from({ length: count }, (_, i) => addDaysToDateString(firstWeekMonday, 7 * i));
}

/** 0-based week index of a Monday relative to the plan's first Monday. */
export function weekIndexOf(firstWeekMonday: string, weekMonday: string): number {
  return Math.round(daysBetweenDateStrings(firstWeekMonday, weekMonday) / 7);
}
