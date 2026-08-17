/**
 * Proof that the recording pipeline works, end to end, before any real demo
 * footage depends on it.
 *
 * It signs in to the **live Cloud Run frontend** with a real test account and
 * walks to the dashboard, recording the whole thing at 1920×1080. Nothing here
 * is a rehearsal of the demo script — the point is only that a watchable file
 * comes out the other end, with the pauses in it that were asked for.
 *
 * Why the pauses matter enough to be in a smoke test: Playwright encodes video
 * from a screencast stream, so a frame is only emitted when something changes.
 * A script that clicks through instantly produces a file that is technically
 * valid and useless to watch. Holding still before and after the action is what
 * proves the recorder is capturing a *session* rather than a slideshow of two
 * states — and it is how the real footage will have to be paced anyway.
 *
 * Usage:  node record-smoke.mjs [email] [password]
 * Output: out/smoke-YYYY... .webm, plus stills alongside it for a quick look.
 */

import { existsSync, mkdirSync, readdirSync, renameSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { chromium } from 'playwright'

const APP = process.env.APP_URL ?? 'https://steward-frontend-223877730603.us-central1.run.app'
const EMAIL = process.argv[2] ?? 'steward-test-executor@example.com'
const PASSWORD = process.argv[3] ?? 'steward-test-pw-2026'

// 1080p, and the viewport matches the video frame exactly. If they differ,
// Playwright letterboxes the page inside the frame and the recording carries
// black bars nobody asked for.
const SIZE = { width: 1920, height: 1080 }

const OUT = resolve('out')
if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true })

/** Hold still, on purpose, so the encoder has something to encode. */
const beat = (page, ms, why) => {
  console.log(`  … holding ${ms}ms — ${why}`)
  return page.waitForTimeout(ms)
}

const browser = await chromium.launch()
const context = await browser.newContext({
  viewport: SIZE,
  recordVideo: { dir: OUT, size: SIZE },
  // A recording is a demo asset: it should show the app at the size a viewer's
  // screen is, not at whatever DPR this machine happens to have.
  deviceScaleFactor: 1,
})
const page = await context.newPage()

const problems = []
page.on('pageerror', (e) => problems.push(String(e)))
page.on('console', (m) => { if (m.type() === 'error') problems.push(m.text()) })

console.log(`recording ${APP} at ${SIZE.width}×${SIZE.height}`)

// --- arrive ----------------------------------------------------------------
await page.goto(APP, { waitUntil: 'networkidle' })
await page.waitForSelector('#email', { timeout: 30000 })
console.log('sign-in rendered')
await beat(page, 2000, 'let the sign-in screen settle before anything moves')

// --- sign in ---------------------------------------------------------------
// Typed rather than filled: a demo viewer should see the field being used.
await page.type('#email', EMAIL, { delay: 40 })
await page.type('#password', PASSWORD, { delay: 40 })
await beat(page, 800, 'a held breath before the click')
await page.click('button[type=submit]')

// --- the one action: land on the dashboard ---------------------------------
await page.waitForSelector('.hero', { timeout: 60000 })
// The estate is only really "there" once something from it has rendered.
await page.waitForSelector('.card, .empty, .notice--problem', { timeout: 60000 })
const heading = (await page.locator('.hero__title').first().innerText()).trim()
console.log(`dashboard rendered — "${heading}"`)
await beat(page, 3000, 'let the dashboard be read, the way a viewer would')

await page.screenshot({ path: join(OUT, 'smoke-dashboard.png') })

// --- close, which is what finalises the video ------------------------------
const video = page.video()
await context.close()
await browser.close()

const raw = await video.path()
const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
const final = join(OUT, `smoke-${stamp}.webm`)
renameSync(raw, final)

const { size } = statSync(final)
console.log(`\nvideo: ${final}`)
console.log(`bytes: ${size.toLocaleString()}`)
console.log(`out/ : ${readdirSync(OUT).join(', ')}`)
console.log(`page errors: ${problems.length ? problems.join(' | ') : 'none'}`)

if (size < 50_000) {
  console.error('\nThat file is too small to be a real recording. Check ffmpeg.')
  process.exit(1)
}
