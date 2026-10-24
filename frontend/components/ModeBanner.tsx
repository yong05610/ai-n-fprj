"use client";

import { useEffect, useState } from "react";

import { API_BASE_URL } from "@/lib/api";
import { type HealthState, modeBannerLines, parseHealth } from "@/lib/modeBanner";

const HEALTH_TIMEOUT_MS = 5_000;
const frontendDev = process.env.NEXT_PUBLIC_AUTH_MODE === "dev";

/**
 * A light band under the top bar that says when the app runs in a development mode (dev auth or
 * in-memory storage), so nobody mistakes a server that forgets its data for a persistent one.
 * It reads GET /health once; nothing is shown for a Firebase / Firestore server.
 */
export function ModeBanner() {
  const [health, setHealth] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false; // the screen was left before /health answered
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    (async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/health`, { signal: controller.signal });
        const modes = response.ok ? parseHealth(await response.json().catch(() => null)) : null;
        if (!cancelled) setHealth(modes ? { status: "ok", modes } : { status: "failed" });
      } catch {
        if (!cancelled) setHealth({ status: "failed" });
      } finally {
        clearTimeout(timer);
      }
    })();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, []);

  const lines = modeBannerLines(health, frontendDev);
  if (lines.length === 0) return null;
  return (
    <div className="mode-banner" role="status" aria-label="실행 모드 안내">
      {lines.map((line) => (
        <span key={line}>{line}</span>
      ))}
    </div>
  );
}
