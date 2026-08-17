import { useRef, useState } from 'react'

import { ApiError, addEstateItem, photoConcern } from '../api'
import { ESTATE_ID } from '../firebase'
import type { Item } from '../types'

/** Add a belonging to the estate, from a photograph.
 *
 * The whole thing starts here: one photograph in, one item out. Executor only —
 * cataloguing is their job, the same gate the photo and disposition actions use.
 *
 * The wait is real and it is not short. A photograph goes to Cloud Storage and
 * then to Gemini, and that takes a few seconds on a good day. Saying what is
 * happening, in order, beats a spinner that could mean anything — and beats
 * silence entirely.
 */
export function AddItem({ onAdded }: { onAdded: (item: Item) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [stage, setStage] = useState<'idle' | 'uploading' | 'reading'>('idle')
  const [problem, setProblem] = useState<string | null>(null)
  // A photograph the pre-check thought was unusable, held back with the file so
  // the person can look at the message and decide.
  const [concern, setConcern] = useState<{ file: File; message: string } | null>(null)

  const working = stage !== 'idle'

  async function choose(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    // Reset immediately: without this, picking the same file twice in a row
    // fires no change event and the second upload silently never happens.
    event.target.value = ''
    if (!file) return
    await send(file, false)
  }

  async function send(file: File, acceptAnyway: boolean) {
    setProblem(null)
    setConcern(null)
    setStage('uploading')
    // The two halves of the wait are worth naming separately — the second one
    // is where the time actually goes, and "Steward is looking at it" is a
    // truer account of the pause than "Loading…".
    const reading = window.setTimeout(() => setStage('reading'), 1200)
    try {
      onAdded(await addEstateItem(ESTATE_ID, file, acceptAnyway))
    } catch (error) {
      // The pre-check's verdict is an offer, not a refusal: hold the file and
      // let them look at the picture again, or overrule it.
      const flagged = photoConcern(error)
      if (flagged) setConcern({ file, message: flagged.message })
      else
        setProblem(
          error instanceof ApiError ? error.message : `Couldn't add that one: ${error}`,
        )
    } finally {
      window.clearTimeout(reading)
      setStage('idle')
    }
  }

  return (
    <div className="add-item">
      <input
        ref={input}
        id="add-item-file"
        className="add-item__file"
        type="file"
        accept="image/jpeg,image/png,image/webp,image/heic"
        onChange={(event) => void choose(event)}
        disabled={working}
        aria-label="Photograph of the belonging to add"
      />
      <button
        className="button button--primary"
        type="button"
        disabled={working}
        onClick={() => input.current?.click()}
      >
        {stage === 'uploading'
          ? 'Sending the photo…'
          : stage === 'reading'
            ? 'Steward is looking at it…'
            : 'Add an item'}
      </button>

      {working && (
        <p className="add-item__note" role="status">
          This takes a few seconds — Steward reads the photograph and works out
          what the thing is. No need to wait on it if you'd rather carry on.
        </p>
      )}

      {concern && (
        <div className="add-item__concern" role="status">
          <p className="add-item__concern-text">{concern.message}</p>
          <div className="add-item__concern-actions">
            <button
              className="button button--sage"
              type="button"
              disabled={working}
              onClick={() => input.current?.click()}
            >
              Pick another
            </button>
            {/* Believed, not argued with. The check is a convenience and it can
                be wrong; someone who knows their photograph is fine says so
                once and it goes through. */}
            <button
              className="button button--quiet"
              type="button"
              disabled={working}
              onClick={() => void send(concern.file, true)}
            >
              Use it anyway
            </button>
          </div>
        </div>
      )}

      {problem && (
        <p className="add-item__problem" role="alert">
          {problem}
        </p>
      )}
    </div>
  )
}
