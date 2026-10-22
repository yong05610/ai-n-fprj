"use client";

export type GoalOption = { id: string; course: string; start_date: string; target_date: string; status: string };

/**
 * Small "현재 학습" switcher shown on the plan/execution screens only (docs/multi_goal_design.md F).
 * The selection is saved as users.active_goal_id by the parent; this component only renders.
 * With a single learning it shows the name instead of a dropdown.
 */
export function GoalSwitch({
  goals,
  activeGoalId,
  busy,
  onSelect,
}: {
  goals: GoalOption[];
  activeGoalId: string | null;
  busy: boolean;
  onSelect: (goalId: string) => void;
}) {
  const options = goals.filter((g) => g.status === "active");
  if (options.length === 0) return null;
  const current = options.find((g) => g.id === activeGoalId);

  return (
    <div className="goal-switch">
      <label htmlFor="goal-switch-select">현재 학습</label>
      {options.length === 1 ? (
        <strong>{options[0].course}</strong>
      ) : (
        <select
          id="goal-switch-select"
          aria-label="학습 전환"
          value={current?.id ?? ""}
          disabled={busy}
          onChange={(e) => onSelect(e.target.value)}
        >
          {!current && (
            <option value="" disabled>
              학습을 선택하세요
            </option>
          )}
          {options.map((g) => (
            <option key={g.id} value={g.id}>
              {g.course}
            </option>
          ))}
        </select>
      )}
      <small>선택한 학습의 계획·기록을 보여줘요</small>
    </div>
  );
}
