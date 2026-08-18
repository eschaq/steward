/** Beat 3 — someone says the thing that makes an object theirs, and Steward
 * notices, and asks the rest of the family for one of their own. Once. */
import { ITEM, bringIntoView, hold, recordBeat, write } from './lib.mjs'

await recordBeat({
  name: 'beat3-memory',
  perform: async (page) => {
    await page.goto(`${page.url().split('/').slice(0, 3).join('/')}/items/${ITEM.woodenBox}`, {
      waitUntil: 'networkidle',
    })
    await page.waitForSelector('#item-note', { timeout: 40000 })
    await hold(page, 2400, 'the wooden box')

    await bringIntoView(page, '#item-note')
    await write(
      page,
      '#item-note',
      "He kept his cufflinks in this, and I remember the smell of the cedar every time he opened it before church.",
    )
    await hold(page, 1600, 'the memory, before it is sent')
    await page.click('.compose button[type=submit], .compose__text ~ button, form.compose button')

    // Steward decides whether that was a memory, then writes its invitation.
    await page.waitForSelector('text=/remember|anyone else|one of your own/i', { timeout: 90000 })
    await hold(page, 1000, 'let it land')
    await bringIntoView(page, 'text=/remember|anyone else|one of your own/i')
    await hold(page, 4000, "Steward's invitation, long enough to read")
  },
})
