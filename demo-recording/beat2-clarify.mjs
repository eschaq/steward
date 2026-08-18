/** Beat 2 — Steward couldn't place a photograph and said so. A person answers
 * in their own words, and the item comes back identified. */
import { ITEM, hold, recordBeat, write } from './lib.mjs'

await recordBeat({
  name: 'beat2-clarify',
  perform: async (page) => {
    await page.goto(`${page.url().split('/').slice(0, 3).join('/')}/items/${ITEM.unknown}`, {
      waitUntil: 'networkidle',
    })
    await page.waitForSelector('#answer-steward', { timeout: 40000 })
    await hold(page, 2600, "the item Steward couldn't place, and its question")

    await write(
      page,
      '#answer-steward',
      "It's a stoneware mixing bowl — cream glaze with a blue band, the one she made bread in every Sunday.",
    )
    await hold(page, 1400, 'the answer, written out')
    await page.click('.answer button[type=submit], .answer__foot button')

    await page.waitForSelector('.answer-outcome', { timeout: 90000 })
    await hold(page, 3600, 'what Steward made of it')
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForSelector('.placard', { timeout: 40000 })
    await hold(page, 3200, 'the item, now identified')
  },
})
