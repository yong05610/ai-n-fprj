"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import type { GoalOption } from "@/components/GoalSwitch";
import { ApiError, apiRequest } from "@/lib/api";

/**
 * Data and the switch action for the "현재 학습" widget on screens that do not already load
 * the learning list themselves (the path screen). The selection is saved as users.active_goal_id.
 */
export function useGoalSwitch() {
  const { session } = useAuth();
  const [goals, setGoals] = useState<GoalOption[]>([]);
  const [activeGoalId, setActiveGoalId] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!session) return;
    try {
      const token = await session.getToken();
      const [goalList, profile] = await Promise.all([
        apiRequest<GoalOption[]>("/api/goals", { token }),
        apiRequest<{ active_goal_id: string | null }>("/api/user/profile", { token }),
      ]);
      setGoals(goalList);
      setActiveGoalId(profile.active_goal_id);
    } catch {
      // The widget is a convenience; the screen it sits on keeps working without it.
      setGoals([]);
    }
  }, [session]);

  useEffect(() => {
    load();
  }, [load]);

  async function switchGoal(goalId: string) {
    if (!session || goalId === activeGoalId || switching) return;
    setSwitching(true);
    setError(null);
    try {
      const token = await session.getToken();
      await apiRequest("/api/user/profile", { method: "PATCH", token, body: { active_goal_id: goalId } });
      setActiveGoalId(goalId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "학습을 전환하지 못했습니다.");
    } finally {
      setSwitching(false);
    }
  }

  return { goals, activeGoalId, switching, error, switchGoal };
}
