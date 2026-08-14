import { chromium } from 'playwright'

const APP = 'http://localhost:5173'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 1400 }, deviceScaleFactor: 1.5 })
const problems = []
page.on('console', (m) => m.type() === 'error' && problems.push(m.text()))
page.on('pageerror', (e) => problems.push(String(e)))

await page.goto(APP, { waitUntil: 'networkidle' })
await page.waitForSelector('#email', { timeout: 20000 })
await page.fill('#email', 'steward-test-executor@example.com')
await page.fill('#password', 'steward-test-pw-2026')
await page.click('button[type=submit]')
await page.waitForSelector('.card', { timeout: 30000 })
console.log('signed in')

// --- reach the Message Center from the dashboard nav ------------------------
await page.locator('.estate-nav__link', { hasText: 'Messages' }).click()
// Wait for the feed itself, not the compose box — the box is static markup and
// renders instantly, so waiting on it snapshots an empty feed.
await page.waitForSelector('.thread-section', { timeout: 25000 })
await page.waitForTimeout(500)
console.log('navigated via nav →', new URL(page.url()).pathname)

const feed = await page.evaluate(() => ({
  heading: document.querySelector('.hero__title')?.textContent?.trim(),
  count: document.querySelector('.thread-section .eyebrow')?.textContent?.trim(),
  entries: [...document.querySelectorAll('.msg')].map((m) => ({
    who: m.querySelector('.msg__who')?.textContent?.trim(),
    agent: m.className.includes('msg--agent'),
    about: m.querySelector('.msg__about')?.textContent?.trim(),
    href: m.querySelector('a.msg__about')?.getAttribute('href') ?? null,
    text: m.querySelector('.msg__text')?.textContent?.trim().slice(0, 52),
  })),
}))

console.log('\n--- unified feed ---')
console.log('heading:', feed.heading, '|', feed.count)
for (const e of feed.entries) {
  console.log(`  ${e.agent ? '[agent]' : '[human]'} ${e.who} — ${e.about}`)
  console.log(`      ${e.href ?? '(general)'} :: ${e.text}…`)
}
await page.screenshot({ path: 'mockups/built/messages.png' })

// --- the item link actually goes somewhere ---------------------------------
const link = page.locator('a.msg__about').first()
const target = await link.getAttribute('href')
await link.click()
await page.waitForSelector('.placard', { timeout: 20000 })
const landed = await page.evaluate(() => ({
  path: location.pathname,
  title: document.querySelector('.placard__title')?.textContent?.trim(),
}))
console.log(`\nlink ${target} → ${landed.path} (${landed.title})`)
await page.goBack()
await page.waitForSelector('.thread-section', { timeout: 25000 })
await page.waitForTimeout(500)

// --- post a general message, live ------------------------------------------
const before = await page.locator('.msg').count()
const text = `Coming by on Saturday to start on the study — ${new Date().toISOString().slice(11, 19)}`
await page.fill('#compose', text)
await page.click('.compose button[type=submit]')
await page.waitForFunction(
  (n) => document.querySelectorAll('.msg').length > n,
  before,
  { timeout: 25000 },
)
await page.waitForTimeout(400)

const after = await page.evaluate(() => {
  const all = [...document.querySelectorAll('.msg')]
  const last = all[all.length - 1]
  return {
    count: all.length,
    who: last.querySelector('.msg__who')?.textContent?.trim(),
    about: last.querySelector('.msg__about')?.textContent?.trim(),
    isLink: Boolean(last.querySelector('a.msg__about')),
    text: last.querySelector('.msg__text')?.textContent?.trim(),
    draftCleared: document.querySelector('#compose').value === '',
    reloaded: performance.getEntriesByType('navigation')[0]?.type,
  }
})
console.log('\n--- after posting (no reload) ---')
console.log('messages     :', before, '→', after.count)
console.log('newest       :', after.who, '|', after.about, '| link:', after.isLink)
console.log('text         :', after.text)
console.log('draft cleared:', after.draftCleared)
console.log('navigation   :', after.reloaded)
await page.screenshot({ path: 'mockups/built/messages-posted.png' })

if (problems.length) { console.log('\nconsole errors:'); problems.forEach((p) => console.log('  -', p)) }
await browser.close()
console.log('\ndone')
