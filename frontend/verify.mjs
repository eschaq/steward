/**
 * Drives the real app in a real browser: sign in as the seeded executor, wait
 * for the dashboard, and report what actually rendered.
 *
 * Not part of the app — a verification harness, kept because "it should work"
 * and "I watched it work" are different claims.
 *
 * Needs both servers running:
 *   cd backend   && .venv/bin/uvicorn api:app --port 8000
 *   cd frontend  && npm run dev
 *
 * Usage: node verify.mjs [email] [password]
 */

import { chromium } from 'playwright'

const APP = process.env.APP_URL ?? 'http://localhost:5173'
const EMAIL = process.argv[2] ?? 'steward-test-executor@example.com'
const PASSWORD = process.argv[3] ?? 'steward-test-pw-2026'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } })

const consoleProblems = []
page.on('console', (m) => {
  if (m.type() === 'error') consoleProblems.push(m.text())
})
page.on('pageerror', (e) => consoleProblems.push(String(e)))

await page.goto(APP, { waitUntil: 'networkidle' })

// --- sign in ---------------------------------------------------------------
await page.waitForSelector('#email', { timeout: 15000 })
await page.waitForTimeout(600) // let webfonts settle before the screenshot
console.log('sign-in screen rendered')
await page.screenshot({ path: 'verify-signin.png', fullPage: false })
await page.fill('#email', EMAIL)
await page.fill('#password', PASSWORD)
await page.click('button[type=submit]')

// --- dashboard -------------------------------------------------------------
await page.waitForSelector('.hero', { timeout: 30000 })
// Wait for the load to actually resolve — a card, an empty state, or a stated
// problem. Waiting on the absence of loading copy is fragile: it passes the
// instant that wording changes.
await page.waitForSelector('.card, .empty, .notice--problem', { timeout: 30000 })
await page.waitForTimeout(400)

const problem = await page.locator('.notice--problem').first()
if (await problem.count()) {
  console.log('PROBLEM BANNER:', (await problem.innerText()).trim())
}

const summary = await page.evaluate(() => {
  const text = (el) => el?.textContent?.trim() ?? ''
  return {
    signedInAs: text(document.querySelector('.hero__email')),
    heading: text(document.querySelector('.hero__title')),
    blurb: [...document.querySelectorAll('.hero__marks .tag')].map((t) => t.textContent.trim()).join(' / '),
    filters: [...document.querySelectorAll('.filter')].map((b) =>
      b.textContent.replace(/\s+/g, ' ').trim(),
    ),
    cardCount: document.querySelectorAll('.card').length,
    ledger: [...document.querySelectorAll('.ledger__block')].map((b) =>
      b.textContent.replace(/\s+/g, ' ').trim(),
    ),
    chips: [...document.querySelectorAll('.card__chip .tag')].reduce((tally, chip) => {
      const key = chip.className.replace('tag tag--', '')
      tally[key] = (tally[key] ?? 0) + 1
      return tally
    }, {}),
    firstCards: [...document.querySelectorAll('.card')].slice(0, 4).map((card) => ({
      category: text(card.querySelector('.card__category')),
      title: text(card.querySelector('.card__title')),
      status: text(card.querySelector('.card__chip .tag')),
    })),
  }
})

console.log('\n--- dashboard ---')
console.log('signed in as :', summary.signedInAs)
console.log('heading      :', summary.heading)
console.log('marks        :', summary.blurb)
console.log('ledger       :', summary.ledger.join('  |  '))
console.log('filters      :', summary.filters.join('  |  '))
console.log('cards        :', summary.cardCount)
console.log('badges       :', JSON.stringify(summary.chips))
console.log('first cards  :')
for (const card of summary.firstCards) {
  console.log(`   [${card.status}] ${card.category} — ${card.title}`)
}

await page.screenshot({ path: 'verify-dashboard.png', fullPage: false })

// --- a filter tab actually filters -----------------------------------------
const contested = page.locator('.filter', { hasText: 'Needs a talk' }).first()
await contested.click()
await page.waitForTimeout(300)
const afterFilter = await page.evaluate(() => ({
  cards: document.querySelectorAll('.card').length,
  statuses: [...new Set([...document.querySelectorAll('.card__chip .tag')].map((c) => c.textContent.trim()))],
  empty: document.querySelector('.empty')?.textContent?.trim() ?? null,
}))
console.log('\n--- Needs a talk filter ---')
console.log('cards        :', afterFilter.cards)
console.log('statuses     :', afterFilter.statuses.join(', ') || '(none)')
if (afterFilter.empty) console.log('empty state  :', afterFilter.empty)
await page.screenshot({ path: 'verify-contested.png', fullPage: false })

if (consoleProblems.length) {
  console.log('\nconsole errors:')
  for (const problem of consoleProblems) console.log('  -', problem)
}

await browser.close()
console.log('\ndone')
