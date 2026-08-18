/** Beat 1 — two people want the mantel clock, and Steward has already offered a
 * way through. Nothing is performed here but reading: the beat is the agent's
 * own words sitting in the family's thread. */
import { ITEM, bringIntoView, hold, recordBeat } from './lib.mjs'

await recordBeat({
  name: 'beat1-mediation',
  perform: async (page) => {
    await bringIntoView(page, '.card:has-text("Mantel Clock")')
    await hold(page, 1400, 'the clock on the shelf of things')
    await page.click('.card:has-text("Mantel Clock") a, .card:has-text("Mantel Clock")')
    await page.waitForSelector('.placard, .msg, .thread', { timeout: 40000 })
    await hold(page, 2600, 'the clock, and that it needs a talk')

    await bringIntoView(page, 'text=have both asked for this one')
    await hold(page, 3400, "Steward's mediation, long enough to read it")
    await page.mouse.wheel(0, 260)
    await hold(page, 2800, 'the rest of what it suggests')
  },
})
