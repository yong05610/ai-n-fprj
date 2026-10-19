/**
 * sessionStorage persistence for the in-progress learning-path wizard (P4-7).
 * Wrapped in try/catch throughout: sessionStorage can throw (private browsing,
 * storage disabled) and the wizard must still work with persistence simply
 * not happening in that case.
 */

const STORAGE_KEY = "pacemate-plan-wizard-draft";

export function saveWizardDraft<T>(value: T): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Persistence unavailable - the wizard still works for this single session.
  }
}

export function loadWizardDraft<T>(): T | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function clearWizardDraft(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
