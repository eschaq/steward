/** Beat 3 — someone says the thing that makes an object theirs, and Steward
 * notices, and asks the rest of the family for one of their own. Once. */
import { ITEM, bringIntoView, hold, recordBeat, write } from './lib.mjs'

await recordBeat({
  name: 'beat3-memory',
  perform: async (page) => {
    await page.goto(`${page.url().split('/').slice(0, 3).join('/')}/items/${ITEM.sewingMachine}`, {
      waitUntil: 'networkidle',
    })
    await page.waitForSelector('#item-note', { timeout: 40000 })
    await hold(page, 2400, 'the sewing machine')

    await bringIntoView(page, '#item-note')
    await write(
      page,
      '#item-note',
      "She made every one of our school uniforms on this, and I can still hear it going in the back room on a Sunday night.",
    )
    await hold(page, 1600, 'the memory, before it is sent')
    await page.click('.compose button[type=submit], .compose__text ~ button, form.compose button')

    // Wait for Steward's own message to arrive in the thread — scoped to the
    // author line, because the compose box is labelled "Anything you remember
    // about it", and a text match wide enough to catch the invitation also
    // catches that label. It did, and the first take held on "Posting…".
    await page.waitForSelector('.msg__who:text-is("Steward")', { timeout: 120000 })
    await hold(page, 1200, 'let it land')
    await bringIntoView(page, '.msg__who:text-is("Steward")')
    await hold(page, 4000, "Steward's invitation, long enough to read")
  },
})
