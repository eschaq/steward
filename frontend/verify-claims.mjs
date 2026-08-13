import { chromium } from 'playwright'

const APP = 'http://localhost:5173'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 1200 }, deviceScaleFactor: 1.5 })
const problems = []
page.on('console', (m) => m.type() === 'error' && problems.push(m.text()))
page.on('pageerror', (e) => problems.push(String(e)))

await page.goto(APP, { waitUntil: 'networkidle' })
await page.waitForSelector('#email', { timeout: 20000 })
await page.fill('#email', 'steward-test-executor@example.com')
await page.fill('#password', 'steward-test-pw-2026')
await page.click('button[type=submit]')
await page.waitForSelector('.card', { timeout: 30000 })

async function inspect(itemId, shot) {
  await page.goto(`${APP}/items/${itemId}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.placard', { timeout: 20000 })
  await page.waitForTimeout(700)
  const data = await page.evaluate(() => ({
    title: document.querySelector('.placard__title')?.textContent?.trim(),
    status: document.querySelector('.placard__marks .tag')?.textContent?.trim(),
    stands: document.querySelectorAll('.placard__facts dd')[0]?.textContent?.trim(),
    heading: document.querySelector('.claimants .eyebrow')?.textContent?.trim() ?? null,
    claimants: [...document.querySelectorAll('.claimant')].map((c) => ({
      who: c.querySelector('.claimant__who')?.textContent?.trim(),
      comment: c.querySelector('.claimant__comment')?.textContent?.trim()
        ?? c.querySelector('.claimant__silent')?.textContent?.trim(),
    })),
    mediation: document.querySelector('.msg--prominent .msg__text')?.textContent?.trim().slice(0, 58),
  }))
  console.log(`\n--- ${itemId} ---`)
  console.log('title       :', data.title, '|', data.status)
  console.log('where stands:', data.stands)
  console.log('section     :', data.heading ?? '(not rendered)')
  for (const c of data.claimants) console.log(`   ${c.who} — ${c.comment}`)
  if (data.mediation) console.log('mediation   :', data.mediation + '…')
  await page.screenshot({ path: shot })
}

await inspect('demo-hall-rug', 'mockups/built/item-claimed.png')
await inspect('demo-writing-desk', 'mockups/built/item-contested.png')
await inspect('demo-everyman-books', 'mockups/built/item-unclaimed.png')

if (problems.length) { console.log('\nconsole errors:'); problems.forEach((p) => console.log('  -', p)) }
await browser.close()
console.log('\ndone')
