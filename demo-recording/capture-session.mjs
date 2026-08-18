/**
 * Step one of the Cloud Console beat: sign in **by hand**, once.
 *
 * Google's sign-in actively resists automation — it is meant to — and scripting
 * it would be both unreliable and the wrong thing to build. So this opens a real
 * visible window, gets out of the way while a person signs in, and then saves
 * the authenticated session. `beat7-cloud-console.mjs` loads that and never sees
 * a login page.
 *
 * A **persistent profile** rather than a bare launch: Google is markedly more
 * willing to sign a browser in when it looks like a browser somebody uses, and a
 * fresh incognito-ish context every time is exactly what "this browser or app
 * may not be secure" is looking for. The profile stays in `.auth/profile`, so a
 * second run of this usually needs no interaction at all.
 *
 * Nothing here is committed. `.auth/` holds live Google session cookies and is
 * gitignored — treat that directory the way you would treat a password.
 *
 * Usage:
 *   node capture-session.mjs          # opens a window, waits for you
 */

import { existsSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { chromium } from 'playwright'

export const PROJECT = 'steward-hackathon-505217'
export const AUTH_DIR = resolve('.auth')
export const STATE_FILE = resolve('.auth/gcloud.json')
const PROFILE = resolve('.auth/profile')

const START = `https://console.cloud.google.com/run?project=${PROJECT}`
const WAIT_MINUTES = 15

if (!existsSync(AUTH_DIR)) mkdirSync(AUTH_DIR, { recursive: true })

const context = await chromium.launchPersistentContext(PROFILE, {
  headless: false,
  viewport: { width: 1280, height: 720 },
  // Chromium announces itself as automated by default; Google's sign-in reads
  // that and refuses. This is not evading a security control — it is the same
  // browser, driven by the person sitting in front of it.
  args: [
    '--disable-blink-features=AutomationControlled',
    '--start-maximized',
    '--no-first-run',
    '--no-default-browser-check',
  ],
})

const page = context.pages()[0] ?? (await context.newPage())
await page.goto(START, { waitUntil: 'domcontentloaded' })

console.log(`
  A browser window is open on the Cloud Run page for ${PROJECT}.

  Sign in to Google in that window. Take as long as you need — this waits up
  to ${WAIT_MINUTES} minutes and saves the session the moment the Cloud Run
  service list appears.

  Nothing is typed for you, and nothing about your account is read: only the
  session cookies are saved, into .auth/ , which is gitignored.
`)

// Signed in is not a URL — the console redirects plenty while loading. It is
// the service list actually being on screen.
const signedIn = page
  .locator('text=steward-backend')
  .or(page.locator('text=steward-frontend'))
  .first()

try {
  await signedIn.waitFor({ state: 'visible', timeout: WAIT_MINUTES * 60_000 })
} catch {
  console.error(
    '\n  Never saw the Cloud Run service list. Nothing was saved — run this again.\n',
  )
  await context.close()
  process.exit(1)
}

await page.waitForTimeout(2500) // let the rest of the console settle
await context.storageState({ path: STATE_FILE })
console.log(`  Signed in. Session saved to ${STATE_FILE}`)
console.log('  You can close the window; the recording script runs on its own.\n')
await context.close()
