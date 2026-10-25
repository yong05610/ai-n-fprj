/** How many open requests currently think the server is waking up; the notice shows while it is above 0. */
let count = 0;
const listeners = new Set<() => void>();

export function reportWaiting(waiting: boolean): void {
  count = Math.max(0, count + (waiting ? 1 : -1));
  listeners.forEach((l) => l());
}

export function subscribeWaiting(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function isServerWaking(): boolean {
  return count > 0;
}
