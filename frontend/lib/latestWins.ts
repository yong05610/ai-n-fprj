/**
 * "The last value wins" saving (Phase 5D weekday changes).
 *
 * Changing the same item several times quickly must leave the server with the last choice even
 * if responses arrive in any order. So requests for one key are sent one at a time, and while
 * one is in flight only the newest wanted value is remembered (intermediate values are skipped).
 * Different keys are independent. A failed value is kept for a retry and never rolled back.
 */
export type SaveState = { status: "idle" | "saving" | "saved" | "error"; failedKeys: string[] };

export class LatestWinsSaver<V> {
  private wanted = new Map<string, V>();
  private inFlight = new Set<string>();
  private failed = new Set<string>();
  private touched = false;

  constructor(
    private send: (key: string, value: V) => Promise<void>,
    private onChange: (state: SaveState) => void,
  ) {}

  /** Records the wanted value for a key and makes sure it eventually reaches the server. */
  set(key: string, value: V): void {
    this.touched = true;
    this.wanted.set(key, value);
    this.failed.delete(key);
    this.emit();
    if (!this.inFlight.has(key)) void this.drain(key);
  }

  /** Resends the most recent wanted value of every key that failed. */
  retry(): void {
    for (const key of [...this.failed]) {
      this.failed.delete(key);
      if (!this.inFlight.has(key)) void this.drain(key);
    }
    this.emit();
  }

  state(): SaveState {
    const failedKeys = [...this.failed];
    if (this.inFlight.size > 0) return { status: "saving", failedKeys };
    if (failedKeys.length > 0) return { status: "error", failedKeys };
    return { status: this.touched ? "saved" : "idle", failedKeys };
  }

  private emit(): void {
    this.onChange(this.state());
  }

  private async drain(key: string): Promise<void> {
    this.inFlight.add(key);
    this.emit();
    try {
      for (;;) {
        const value = this.wanted.get(key) as V;
        try {
          await this.send(key, value);
        } catch {
          this.failed.add(key);
          return;
        }
        if (Object.is(this.wanted.get(key), value)) return; // nothing newer was chosen meanwhile
      }
    } finally {
      this.inFlight.delete(key);
      this.emit();
    }
  }
}
