"use client";

import { useServerModes } from "@/components/ServerGate";
import { type HealthState, modeBannerLines } from "@/lib/modeBanner";

const frontendDev = process.env.NEXT_PUBLIC_AUTH_MODE === "dev";

/**
 * A light band under the top bar that says when the app runs in a development mode (dev auth or
 * in-memory storage), so nobody mistakes a server that forgets its data for a persistent one.
 * The modes come from the GET /health answer the server gate already read; nothing is shown for a
 * Firebase / Firestore server.
 */
export function ModeBanner() {
  const modes = useServerModes();
  const health: HealthState = modes ? { status: "ok", modes } : { status: "failed" };
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
