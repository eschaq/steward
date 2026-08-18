/** Beat 6 — the executor settles the contested clock. The end of the arc: two
 * people asked, they talked it through, and someone records what was agreed. */
import { ITEM, bringIntoView, hold, recordBeat, write } from './lib.mjs'

await recordBeat({
  name: 'beat6-resolve',
  perform: async (page) => {
    await page.goto(`${page.url().split('/').slice(0, 3).join('/')}/items/${ITEM.clock}/resolve`, {
      waitUntil: 'networkidle',
    })
    await page.waitForSelector('#recipient', { timeout: 40000 })
    await hold(page, 2600, 'who asked for it, and why')

    await bringIntoView(page, '#recipient')
    await page.selectOption('#recipient', 'rTnff8Qw4yTLkKI9EtPjmmGGl312')
    await hold(page, 1400, 'it goes to Eban')

    await write(
      page,
      '#notes',
      'Agreed at the kitchen table — Eban takes the clock, David gets first pick of the books.',
    )
    await hold(page, 1600, 'what was actually agreed, in their own words')
    await page.click('button[type=submit]')

    await page.waitForSelector('.decided', { timeout: 60000 })
    await bringIntoView(page, '.decided')
    await hold(page, 4000, 'settled, and the record of it')
  },
})
