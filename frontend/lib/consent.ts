export const TERMS_VERSION = "v1.0";

const CONSENT_STORAGE_KEY = "pacemate-consent";

/** Written only after the server has recorded the consent. */
export function hasStoredConsent(): boolean {
  try {
    return localStorage.getItem(CONSENT_STORAGE_KEY) === TERMS_VERSION;
  } catch {
    return false;
  }
}

export function storeConsent(): void {
  try {
    localStorage.setItem(CONSENT_STORAGE_KEY, TERMS_VERSION);
  } catch {
    // Storage unavailable: the user will see the consent modal again next visit.
  }
}

export function clearConsent(): void {
  try {
    localStorage.removeItem(CONSENT_STORAGE_KEY);
  } catch {
    // ignore
  }
}

export const consentPayload = {
  terms_version: TERMS_VERSION,
  privacy_agreed: true,
  ai_use_agreed: true,
};
