import { useState } from 'react'

/** Answering the agent's question about an item it couldn't place.
 *
 * Deliberately not the general compose box. Both post a Message to the same
 * thread, but only this one is *read back* — what goes in here is handed to the
 * classifier with the photograph, and may change what the item is recorded as.
 * Telling someone that up front is the difference between a reply and a thing
 * that quietly rewrites the catalogue.
 *
 * Offered to any accepted member, not just the executor: which uncle owned the
 * carriage clock is exactly the thing a family knows and an executor may not.
 */
export function AnswerSteward({
  onAnswer,
  working,
}: {
  onAnswer: (text: string) => void | Promise<void>
  working: boolean
}) {
  const [text, setText] = useState('')

  async function send() {
    const said = text.trim()
    if (!said) return
    await onAnswer(said)
    setText('')
  }

  return (
    <section className="answer">
      <h2 className="eyebrow">Steward has asked about this one</h2>
      <label className="answer__label" htmlFor="answer-steward">
        Tell it what you know — what the thing is, roughly how old, anything you
        remember. It'll look at the photograph again with what you've said.
      </label>
      <textarea
        id="answer-steward"
        className="answer__text"
        rows={3}
        placeholder="It's my grandmother's carriage clock — French, about 1890…"
        value={text}
        onChange={(event) => setText(event.target.value)}
        disabled={working}
      />
      <div className="answer__foot">
        <button
          className="button button--primary"
          type="button"
          onClick={() => void send()}
          disabled={working || !text.trim()}
        >
          {working ? 'Steward is looking again…' : 'Send this to Steward'}
        </button>
        {/* Said before they commit, not after: this is the one message on the
            page that can change what the item is recorded as. */}
        <p className="answer__note">
          What you write goes in the thread for everyone, and Steward reads it.
        </p>
      </div>
    </section>
  )
}
