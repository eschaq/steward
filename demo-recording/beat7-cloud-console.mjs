/**
 * Beat 7 — the thing running somewhere real.
 *
 * The other six beats are the product. This one is the evidence underneath it:
 * two Cloud Run services with revision histories, live `.run.app` URLs, and
 * request metrics from actual traffic. A demo that only ever shows its own UI
 * leaves "is this deployed, or is it a laptop?" unanswered, and for a hackathon
 * judged on Google Cloud that is the question worth answering out loud.
 *
 * Sign-in is not scripted — see capture-session.mjs. This loads the session that
 * saved and goes straight to the dashboard.
 *
 * Captured 1:1 at 1280×720 like the other beats, and upscaled afterwards. The
 * console is a dense page; holds here are longer than the app beats' because
 * there is more to read and none of it is designed to be read quickly.
 *
 * Usage:
 *   node capture-session.mjs          # once, sign in by hand
 *   node beat7-cloud-console.mjs      # then this, unattended
 */

import { existsSync, mkdirSync, renameSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { chromium } from 'playwright'

const PROJECT = 'steward-hackathon-505217'
const REGION = 'us-central1'
const STATE_FILE = resolve('.auth/gcloud.json')
const OUT = resolve('out')
const VIEWPORT = { width: 1280, height: 720 }

const url = (path) =>
  `https://console.cloud.google.com/run/detail/${REGION}/${path}?project=${PROJECT}`

if (!existsSync(STATE_FILE)) {
  console.error(`\n  No saved session at ${STATE_FILE}.\n  Run: node capture-session.mjs\n`)
  process.exit(1)
}
if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true })

const hold = async (page, ms, why) => {
  console.log(`   … ${ms}ms — ${why}`)
  await page.waitForTimeout(ms)
}

/** The console loads in pieces; "settled" is a heading plus a beat, not
 * networkidle — its telemetry never goes quiet. */
async function settle(page, ms = 3000) {
  await page.waitForLoadState('domcontentloaded')
  await page.waitForTimeout(ms)
}

const browser = await chromium.launch()
const context = await browser.newContext({
  viewport: VIEWPORT,
  recordVideo: { dir: OUT, size: VIEWPORT },
  storageState: STATE_FILE,
  deviceScaleFactor: 1,
})
const page = await context.newPage()

console.log('\n▶ beat7-cloud-console')

// --- the two services, side by side ----------------------------------------
// /run redirects to an Overview page that truncates the service names to
// "steward-back…". The list itself is the shot.
await page.goto(`https://console.cloud.google.com/run/services?project=${PROJECT}`, {
  waitUntil: 'domcontentloaded',
})
await settle(page, 6000)
await hold(page, 5000, 'both services, live, with their regions and URLs')

// --- the backend: metrics, then revisions ----------------------------------
await page.goto(url('steward-backend/metrics'), { waitUntil: 'domcontentloaded' })
// Monitoring draws its charts well after the page reports loaded — the first
// take held on four empty panels reading "0 time series". Wait for a chart to
// actually have ink in it rather than for a duration.
await settle(page, 4000)
try {
  await page.waitForFunction(
    () => !document.body.innerText.includes('0 time series'),
    null,
    { timeout: 45000 },
  )
} catch {
  console.log('   (charts still empty — holding on them anyway)')
}
await hold(page, 6000, 'the backend serving real requests')

await page.goto(url('steward-backend/revisions'), { waitUntil: 'domcontentloaded' })
await settle(page, 5000)
await hold(page, 5000, 'eleven revisions of it, deployed today')

// --- the frontend ----------------------------------------------------------
await page.goto(url('steward-frontend/revisions'), { waitUntil: 'domcontentloaded' })
await settle(page, 5000)
await hold(page, 4500, 'and the frontend, its own service')

const video = page.video()
await context.close()
await browser.close()

const final = join(OUT, 'beat7-cloud-console.webm')
renameSync(await video.path(), final)
const { size } = statSync(final)
console.log(`   → ${final}  ${(size / 1024 / 1024).toFixed(2)} MB`)
if (size < 100_000) {
  console.error('   that file is too small to be a real recording')
  process.exitCode = 1
}
