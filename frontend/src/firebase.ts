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

export const ESTATE_ID = import.meta.env.VITE_ESTATE_ID ?? 'seed-estate-001'
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
