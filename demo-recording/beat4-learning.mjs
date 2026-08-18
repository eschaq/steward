/** Beat 4 — the adaptive loop, which is the product's whole argument.
 *
 * Three chairs given away, then a fourth decided differently, then the panel
 * that shows Steward has noticed. The fourth deliberately differs: the point is
 * not that Steward is obeyed, it is that it learns from being overruled.
 *
 * A wrinkle worth knowing before watching: the classifier wrote three of these
 * as "dining chairs" and one as "dining chair", and the override log counts by
 * exact category. So the pattern forms over the three, and the fourth appears in
 * the quieter "one decision each so far" line rather than as "3 of 4".
 */
import { ITEM, bringIntoView, hold, recordBeat } from './lib.mjs'

const origin = (page) => page.url().split('/').slice(0, 3).join('/')

async function decide(page, itemId, label, why) {
  await page.goto(`${origin(page)}/items/${itemId}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.disposition', { timeout: 40000 })
  await bringIntoView(page, '.disposition')
  await hold(page, 1800, why)
  await page.click(`.disposition__choices button:has-text("${label}")`)
  await page.waitForTimeout(1200)
  await hold(page, 1600, `recorded: ${label}`)
}

await recordBeat({
  name: 'beat4-learning',
  perform: async (page) => {
    for (const [n, id] of ITEM.chairs.entries()) {
      await decide(page, id, 'Give it away', `chair ${n + 1} of the set`)
    }
    // The fourth goes the other way, on purpose.
    await decide(page, ITEM.oddChair, 'Sell it', 'this one is different')

    await page.goto(`${origin(page)}/review/learned`, { waitUntil: 'networkidle' })
    await page.waitForSelector('.learned', { timeout: 60000 })
    await hold(page, 1200, 'let the panel settle')
    await bringIntoView(page, '.learned__patterns, .learned')
    await hold(page, 4200, 'what Steward has learned about this family')
    await page.mouse.wheel(0, 300)
    await hold(page, 3000, 'the decisions it read that from')
  },
})
