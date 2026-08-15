import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { ApiError, fetchEstateMessages, postEstateMessage } from '../api'
import { useAuth } from '../auth'
import { EstateNav } from '../components/EstateNav'
import { MessageThread } from '../components/MessageThread'
import { ESTATE_ID } from '../firebase'
import type { Message } from '../types'

/** The estate's whole feed, in one place.
 *
 * One feed, not two: per the data model, item-specific and general discussion
 * live in the same collection with a nullable `item_id`, and this shows both
 * interleaved by time. Splitting them into tabs would rebuild the separation
 * the data model deliberately avoids.
 *
 * The per-item thread on ItemDetail is the same data filtered to one item, not
 * a different feed.
 */
export function MessageCenter() {
  const { user, leave } = useAuth()
  const [messages, setMessages] = useState<Message[] | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [posting, setPosting] = useState(false)

  const load = useCallback(async () => {
    setProblem(null)
    try {
      const feed = await fetchEstateMessages(ESTATE_ID)
      setMessages(feed.messages)
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't load the feed: ${error}`,
      )
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function onPost(event: FormEvent) {
    event.preventDefault()
    const text = draft.trim()
    if (!text) return

    setProblem(null)
    setPosting(true)
    try {
      const posted = await postEstateMessage(ESTATE_ID, text)
      // Append the server's own copy rather than refetching: it comes back with
      // the author name and timestamp already resolved, so the message appears
      // at once without a round trip that could reorder the feed underneath.
      //
      // Only ever append to a feed we actually have. Appending to `null` would
      // replace the whole feed with the one message just posted — the compose
      // button is disabled until the load resolves for the same reason.
      setMessages((current) => (current === null ? [posted] : [...current, posted]))
      setDraft('')
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't post that: ${error}`,
      )
    } finally {
      setPosting(false)
    }
  }

  return (
    <main className="page">
      <header className="hero hero--slim">
        <div className="hero__top">
          <EstateNav active="messages" />
          <div className="hero__who">
            <span className="hero__email">{user?.email}</span>
            <button
              className="button button--ghost-ink"
              type="button"
              onClick={() => void leave()}
            >
              Sign out
            </button>
          </div>
        </div>

        <div>
          <div className="eyebrow eyebrow--on-ink">{ESTATE_ID}</div>
          <h1 className="display hero__title">Messages</h1>
        </div>
      </header>

      <form className="compose" onSubmit={onPost}>
        <label className="compose__label" htmlFor="compose">
          Say something to the family. Everyone on this estate will see it.
        </label>
        <textarea
          id="compose"
          className="compose__box"
          rows={3}
          placeholder="I'm free the weekend after next if anyone wants to go through the study together."
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          className="button button--primary"
          type="submit"
          disabled={posting || messages === null || draft.trim().length === 0}
        >
          {posting ? 'Posting…' : 'Post to the feed'}
        </button>
      </form>

      {problem && (
        <p className="notice notice--problem" role="alert">
          <span>{problem}</span>
          <button className="button button--sage" type="button" onClick={() => void load()}>
            Try again
          </button>
        </p>
      )}

      {!problem && messages === null && <p className="notice">Reading the feed…</p>}

      {messages !== null && (
        <section className="thread-section">
          <h2 className="eyebrow">
            {messages.length === 1 ? '1 message' : `${messages.length} messages`}
          </h2>
          <MessageThread
            messages={messages}
            showItems
            empty="Nothing said yet. The feed fills up as the family works through the estate."
          />
        </section>
      )}
    </main>
  )
}
