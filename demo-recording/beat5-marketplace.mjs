/** Beat 5 — Tier 2. An item routed to a marketplace comes back with a channel,
 * a reason, a rough price and draft listing copy, in one Gemini call. */
import { ITEM, bringIntoView, hold, recordBeat } from './lib.mjs'

await recordBeat({
  name: 'beat5-marketplace',
  perform: async (page) => {
    await page.goto(`${page.url().split('/').slice(0, 3).join('/')}/items/${ITEM.lamp}`, {
      waitUntil: 'networkidle',
    })
    await page.waitForSelector('.disposition', { timeout: 40000 })
    await bringIntoView(page, '.disposition')
    await hold(page, 2400, 'the lamp, and where it could go')

    await page.click('.disposition__choices button:has-text("Sell it")')
    await hold(page, 1200, 'the decision recorded')

    await page.waitForSelector('.listing', { timeout: 120000 })
    await bringIntoView(page, '.listing')
    await hold(page, 3000, 'where to list it, and why there')
    await page.mouse.wheel(0, 280)
    await hold(page, 4000, 'the price and the draft listing')
  },
})
