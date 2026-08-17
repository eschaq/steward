/** Firebase client SDK, pointed at the Steward project.
 *
 * These config values are browser-side and public by design in any Firebase web
 * app — firestore.rules and the backend's ID token verification are what
 * actually protect data, not the secrecy of this key.
 */

import { initializeApp } from 'firebase/app'
import { getAuth } from 'firebase/auth'

function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(
      `${name} is not set. Copy frontend/.env.example to .env.local and fill it in.`,
    )
  }
  return value
}

export const app = initializeApp({
  apiKey: required('VITE_FIREBASE_API_KEY', import.meta.env.VITE_FIREBASE_API_KEY),
  authDomain: required('VITE_FIREBASE_AUTH_DOMAIN', import.meta.env.VITE_FIREBASE_AUTH_DOMAIN),
  projectId: required('VITE_FIREBASE_PROJECT_ID', import.meta.env.VITE_FIREBASE_PROJECT_ID),
  appId: required('VITE_FIREBASE_APP_ID', import.meta.env.VITE_FIREBASE_APP_ID),
})

/** The frontend never touches Firestore directly — only Auth, and then the
 * backend API. That's the trust boundary the two-service split exists to hold
 * (CLAUDE.md). */
export const auth = getAuth(app)

/** Which estate the app is currently looking at.
 *
 * Was a build-time constant, which is why the product could only ever know one
 * estate. It is now decided at runtime from `GET /me/estates` after sign-in —
 * but the old value is still the fallback, so an existing account with exactly
 * one estate behaves precisely as it did before.
 *
 * Kept in localStorage so a refresh doesn't lose it before `<Arrival>` has
 * asked again, and cleared on sign-out: on a shared machine the next person
 * must not inherit the last one's estate.
 */
const FALLBACK_ESTATE = import.meta.env.VITE_ESTATE_ID ?? 'seed-estate-001'
const ESTATE_KEY = 'steward.estate'

let currentEstate: string =
  (typeof localStorage !== 'undefined' && localStorage.getItem(ESTATE_KEY)) ||
  FALLBACK_ESTATE

/** Read as a function, never captured as a module constant — a `const` snapshot
 * would freeze whichever estate was current when the module first loaded. */
export function estateId(): string {
  return currentEstate
}

export function setEstateId(id: string): void {
  currentEstate = id
  try {
    localStorage.setItem(ESTATE_KEY, id)
  } catch {
    // Private browsing, a full quota — the in-memory value still works for
    // this session, which is the part that matters.
  }
}

export function clearEstateId(): void {
  currentEstate = FALLBACK_ESTATE
  try {
    localStorage.removeItem(ESTATE_KEY)
  } catch {
    /* nothing to do */
  }
}
/** Where the backend lives.
 *
 * Defaults to *the host you are browsing from*, port 8000 — not a hardcoded
 * `localhost`. On a phone reaching this over the network, `localhost` means the
 * phone itself, so a hardcoded value silently points the app at nothing.
 *
 * Set VITE_API_BASE_URL to override, which is what a deployed frontend will do
 * once the backend has its own Cloud Run URL.
 */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  `${window.location.protocol}//${window.location.hostname}:8000`
