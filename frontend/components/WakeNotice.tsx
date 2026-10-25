"use client";

import { useSyncExternalStore } from "react";

import { PREPARING_MESSAGE } from "@/lib/coldStart";
import { isServerWaking, subscribeWaiting } from "@/lib/serverWake";

/** The "server is getting ready" band for an app that is already open (the gate covers the first open). */
export function WakeNotice() {
  const waking = useSyncExternalStore(subscribeWaiting, isServerWaking, () => false);
  if (!waking) return null;
  return (
    <div className="mode-banner server-notice" role="status">
      <span>{PREPARING_MESSAGE}</span>
    </div>
  );
}
