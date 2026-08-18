/**
 * Shared recording rig for the demo beats.
 *
 * One beat per script, one file per beat. The scripts below differ only in what
 * they *do*; everything about how it is captured lives here so six recordings
 * cut together without a jump in size, pacing, or chrome.
 *
 * **1280×720 viewport, 1920×1080 video.** The smoke test's finding: the app is
 * a centred 1120px column, so capturing at a 1920-wide viewport spent ~800px on
 * empty cream. 1280×720 is an exact 1.5× scale of the frame — same aspect, no
 * letterboxing, and the content fills it.
 *
 * **Pauses are the point.** Playwright encodes from a screencast, so frames are
 * emitted when something changes; a script that clicks straight through
 * produces a valid file nobody can follow. `hold()` is used at the moments that
 * carry meaning — after a page settles, after the agent says something — not
 * merely between clicks.
 */

import { existsSync, mkdirSync, renameSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { chromium } from 'playwright'

export const APP =
  process.env.APP_URL ?? 'https://steward-frontend-223877730603.us-central1.run.app'

/** Eleanor's House, and the items each beat is about. */
export const ESTATE = 'sanKiYo4TrFbHby3vMMk'
export const ITEM = {
  clock: '2jFMSQr3vsyodwISiFW2', // mantel clock, contested by Eban and David
  unknown: 'oLJmgaPl3TdGoCTjq6tD', // the ceramic Steward couldn't place
  woodenBox: 'PpxByuIfOwvnNwBIpoIR',
  sewingMachine: 'NVpGYVflQdzrZmPtWJCv',
  lamp: 'CWch3wouRxPJYJDxvdhe', // the one routed to a marketplace
  // Three share the category "dining chairs"; the fourth is "dining chair",
  // which the classifier wrote differently. See beat4 for what that means.
  chairs: ['MZhUuHil2Qpu3rDPcZgn', 'NMvMFwvypvPS5bs6Ad8O', 'jHK7cUIPN0XsZD0Ui46U'],
  oddChair: 'WBiqQBuPXe8m05wWG8sU',
}

export const EXECUTOR = 'steward-test-executor@example.com'
export const PASSWORD = 'steward-test-pw-2026'

const OUT = resolve('out')
// Video size must EQUAL the viewport. The README guessed that a 1280x720
// viewport recorded at 1920x1080 would scale up 1.5x; it does not — Playwright
// pins the page to the top-left of the larger canvas and fills the rest with
// grey. Captured 1:1 here and upscaled to 1080p afterwards with ffmpeg, which
// is where scaling belongs anyway.
const VIEWPORT = { width: 1280, height: 720 }
const SIZE = { ...VIEWPORT }

/** Hold still, on purpose, so the encoder has something to encode and a viewer
 * has time to read. */
export async function hold(page, ms, why) {
  console.log(`   … ${ms}ms — ${why}`)
  await page.waitForTimeout(ms)
}

/** Type the way a person does, so the field fills on camera instead of
 * blinking from empty to full. */
export async function write(page, selector, text) {
  await page.click(selector)
  await page.type(selector, text, { delay: 28 })
}

/** Scroll something into the middle of frame and let the motion settle. */
export async function bringIntoView(page, selector) {
  await page.locator(selector).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(700)
}

/**
 * Run one beat. Signs in, hands the page to `perform`, then finalises the file.
 *
 * The sign-in is part of every take deliberately: each beat is a self-contained
 * clip that can be shown on its own, and starting from the gable is how the
 * product introduces itself.
 */
export async function recordBeat({ name, as = EXECUTOR, perform }) {
  if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true })

  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: VIEWPORT,
    recordVideo: { dir: OUT, size: SIZE },
    deviceScaleFactor: 1,
  })
  // This account also belongs to the seeded estate, and arrival picks whichever
  // was last chosen — otherwise the oldest, which is not this one. Pinning it
  // before any page script runs lands every beat in Eleanor's House without
  // spending footage on a switcher.
  await context.addInitScript((id) => {
    try { localStorage.setItem('steward.estate', id) } catch {}
  }, ESTATE)

  const page = await context.newPage()

  const problems = []
  page.on('pageerror', (e) => problems.push(String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(m.text())
  })

  console.log(`\n▶ ${name} — as ${as}`)
  await page.goto(APP, { waitUntil: 'networkidle' })
  await page.waitForSelector('#email', { timeout: 40000 })
  await hold(page, 1600, 'let the gable settle before anything moves')

  await write(page, '#email', as)
  await write(page, '#password', PASSWORD)
  await hold(page, 700, 'a breath before signing in')
  await page.click('button[type=submit]')

  // Whatever the account lands on: the dashboard, or a welcome.
  await page.waitForSelector('.card, .empty, .welcome__title', { timeout: 60000 })
  if (await page.locator('.welcome__skip').count()) {
    await page.locator('.welcome__skip').click()
    await page.waitForSelector('.card, .empty', { timeout: 40000 })
  }
  await hold(page, 1800, 'arrive in the estate')

  await perform(page)

  const video = page.video()
  await context.close()
  await browser.close()

  const raw = await video.path()
  const final = join(OUT, `${name}.webm`)
  renameSync(raw, final)
  const { size } = statSync(final)
  console.log(`   → ${final}  ${(size / 1024 / 1024).toFixed(2)} MB`)
  console.log(`   page errors: ${problems.length ? problems.join(' | ') : 'none'}`)
  if (size < 100_000) {
    console.error('   that file is too small to be a real recording')
    process.exitCode = 1
  }
}
