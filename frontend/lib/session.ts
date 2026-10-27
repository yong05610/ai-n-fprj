/**
 * Anonymous session handling.
 *
 * NEXT_PUBLIC_AUTH_MODE
 * - "firebase" (default): Firebase Anonymous Authentication; ID tokens go to the backend.
 * - "dev": local development without Firebase. Uses a random UID and "dev-<uid>" tokens,
 *   which the backend accepts only when it also runs with AUTH_MODE=dev.
 */
import { getApp, getApps, initializeApp } from "firebase/app";
import { type Auth, type User, getAuth, signInAnonymously, signInWithCustomToken, signOut } from "firebase/auth";

import { devUidFromToken } from "@/lib/passwordLogin";

export type Session = {
  uid: string;
  getToken: () => Promise<string>;
};

const isDevMode = process.env.NEXT_PUBLIC_AUTH_MODE === "dev";
const DEV_UID_KEY = "pacemate-dev-uid";

function firebaseAuth(): Auth {
  const config = {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  };
  if (!config.apiKey || !config.projectId) {
    throw new Error("Firebase 설정(NEXT_PUBLIC_FIREBASE_*)이 없습니다.");
  }
  return getAuth(getApps().length ? getApp() : initializeApp(config));
}

function fromFirebaseUser(user: User): Session {
  return { uid: user.uid, getToken: () => user.getIdToken() };
}

function devSession(uid: string): Session {
  return { uid, getToken: async () => `dev-${uid}` };
}

/** Returns the existing anonymous session without creating a new UID. */
export async function restoreSession(): Promise<Session | null> {
  if (isDevMode) {
    const uid = localStorage.getItem(DEV_UID_KEY);
    return uid ? devSession(uid) : null;
  }
  const auth = firebaseAuth();
  await auth.authStateReady();
  return auth.currentUser ? fromFirebaseUser(auth.currentUser) : null;
}

/** Creates the anonymous UID. Call only after the user has accepted the consent notice. */
export async function startAnonymousSession(): Promise<Session> {
  if (isDevMode) {
    const uid = crypto.randomUUID();
    localStorage.setItem(DEV_UID_KEY, uid);
    return devSession(uid);
  }
  const credential = await signInAnonymously(firebaseAuth());
  return fromFirebaseUser(credential.user);
}

/**
 * Signs in with the custom token the server issued after a password login (CR-005). It never creates an
 * anonymous UID: the UID is the one the server found. Dev mode: the token is "dev-<uid>".
 */
export async function signInWithPasswordToken(customToken: string): Promise<Session> {
  if (isDevMode) {
    const uid = devUidFromToken(customToken);
    if (!uid) throw new Error("로그인 응답이 올바르지 않아요. 다시 시도해 주세요.");
    localStorage.setItem(DEV_UID_KEY, uid);
    return devSession(uid);
  }
  const credential = await signInWithCustomToken(firebaseAuth(), customToken);
  return fromFirebaseUser(credential.user);
}

export async function endSession(): Promise<void> {
  if (isDevMode) {
    localStorage.removeItem(DEV_UID_KEY);
    return;
  }
  await signOut(firebaseAuth());
}
