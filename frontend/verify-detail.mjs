/**
 * Drives the dashboard → item detail → claim flow in a real browser.
 *
 * Needs both servers running. Usage: node verify-detail.mjs
 */

import { chromium } from 'playwright'

const APP = process.env.APP_URL ?? 'http://localhost:5173'
const EMAIL = 'steward-test-executor@example.com'
const PASSWORD = 'steward-test-pw-2026'
// An unspoken-for demo item, claimed for real below.
const CLAIM_TARGET = 'demo-hall-rug'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 1100 }, deviceScaleFactor: 1.5 })
const problems = []
page.on('console', (m) => m.type() === 'error' && problems.push(m.text()))
page.on('pageerror', (e) => problems.push(String(e)))

await page.goto(APP, { waitUntil: 'networkidle' })
await page.waitForSelector('#email', { timeout: 20000 })
await page.fill('#email', EMAIL)
await page.fill('#password', PASSWORD)
await page.click('button[type=submit]')
await page.waitForSelector('.card', { timeout: 30000 })
console.log('signed in, dashboard rendered')

// --- 1. navigate by clicking a card -----------------------------------------
await page.locator('.filter', { hasText: 'Needs a talk' }).first().click()
await page.waitForTimeout(400)
await page.locator('.card').first().click()
await page.waitForSelector('.placard', { timeout: 20000 })
await page.waitForTimeout(700)

const detail = await page.evaluate(() => ({
  url: location.pathname,
  title: document.querySelector('.placard__title')?.textContent?.trim(),
  marks: [...document.querySelectorAll('.placard__marks .tag')].map((t) => t.textContent.trim()),
  notes: document.querySelector('.placard__notes')?.textContent?.trim().slice(0, 70),
  facts: [...document.querySelectorAll('.placard__facts div')].map((d) => ({
    label: d.querySelector('dt')?.textContent?.trim(),
    value: d.querySelector('dd')?.textContent?.trim(),
  })),
  messages: [...document.querySelectorAll('.msg')].map((m) => ({
    who: m.querySelector('.msg__who')?.textContent?.trim(),
    agent: m.className.includes('msg--agent'),
    prominent: m.className.includes('msg--prominent'),
    text: m.querySelector('.msg__text')?.textContent?.trim().slice(0, 62),
  })),
  claimable: Boolean(document.querySelector('.claim')),
}))

console.log('\n--- contested item detail ---')
console.log('url        :', detail.url)
console.log('title      :', detail.title)
console.log('marks      :', detail.marks.join(' / '))
console.log('notes      :', detail.notes + '…')
for (const f of detail.facts) console.log(`  ${f.label}: ${f.value}`)
console.log('messages   :', detail.messages.length)
for (const m of detail.messages) {
  console.log(`   ${m.prominent ? '★ ' : '  '}${m.agent ? '[agent]' : '[human]'} ${m.who}: ${m.text}…`)
}
console.log('claim form :', detail.claimable)
await page.screenshot({ path: 'mockups/built/item-contested.png' })

// --- 2. claim an unspoken-for item, for real --------------------------------
await page.goto(`${APP}/items/${CLAIM_TARGET}`, { waitUntil: 'networkidle' })
await page.waitForSelector('.placard', { timeout: 20000 })
await page.waitForTimeout(500)

const before = await page.evaluate(() => ({
  status: document.querySelector('.placard__marks .tag')?.textContent?.trim(),
  messages: document.querySelectorAll('.msg').length,
}))
console.log('\n--- before claiming', CLAIM_TARGET, '---')
console.log('status     :', before.status, '| messages:', before.messages)
await page.screenshot({ path: 'mockups/built/item-unclaimed.png' })

await page.fill('#claim-comment', 'It ran the length of the hall for as long as I can remember.')
await page.click('.claim .button')
await page.waitForFunction(
  () => document.querySelector('.placard__marks .tag')?.textContent?.trim() !== 'Unspoken for',
  { timeout: 25000 },
)
await page.waitForTimeout(500)

const after = await page.evaluate(() => ({
  status: document.querySelector('.placard__marks .tag')?.textContent?.trim(),
  messages: document.querySelectorAll('.msg').length,
  claimable: Boolean(document.querySelector('.claim')),
}))
console.log('\n--- after claiming ---')
console.log('status     :', after.status, '| messages:', after.messages)
console.log('claim form still shown:', after.claimable)
await page.screenshot({ path: 'mockups/built/item-claimed.png' })

if (problems.length) {
  console.log('\nconsole errors:')
  for (const p of problems) console.log('  -', p)
}

await browser.close()
console.log('\ndone')
