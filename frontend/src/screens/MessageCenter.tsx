import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { ApiError, fetchEstateMessages, fetchMe, postEstateMessage } from '../api'
import { useAuth } from '../auth'
import { EstateNav } from '../components/EstateNav'
import { EstateSwitcher } from '../components/EstateSwitcher'
import { MessageThread } from '../components/MessageThread'
import { estateId } from '../firebase'
import type { Me, Message } from '../types'

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
  // Only for the estate's name in the hero — the feed itself needs no role.
  const [me, setMe] = useState<Me | null>(null)

  const load = useCallback(async () => {
    setProblem(null)
    try {
      const [body, standing] = await Promise.all([
        fetchEstateMessages(estateId()),
        fetchMe(estateId()),
      ])
      setMe(standing)
      setMessages(body.messages)
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
      // Append the server's own copy rather than refetching: it comes back with
      // the author name and timestamp already resolved, so it appears at once
      // without a round trip that could reorder the feed underneath.
      const posted = await postEstateMessage(estateId(), text)
      setMessages((current) => (current ? [...current, posted] : current))
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
          <EstateSwitcher name={me?.estate_name ?? estateId()} />
          <h1 className="display hero__title">Messages</h1>
        </div>
      </header>

      {problem && (
        <p className="notice notice--problem" role="alert">
          <span>{problem}</span>
          <button className="button button--sage" type="button" onClick={() => void load()}>
            Try again
          </button>
        </p>
      )}

      <section className="compose">
        <label className="compose__label" htmlFor="compose-text">
          Say something to the family. Everyone on this estate will see it.
        </label>
        <textarea
          id="compose-text"
          className="compose__text"
          rows={3}
          placeholder="I'm free the weekend after next if anyone wants to go through the study together."
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <button
          className="button button--primary"
          type="button"
          onClick={(event) => void onPost(event)}
          disabled={posting || !draft.trim() || messages === null}
        >
          {posting ? 'Posting…' : 'Post to the feed'}
        </button>
      </section>

      {messages !== null && (
        <section className="thread-section">
          <h2 className="eyebrow">
            {messages.length} {messages.length === 1 ? 'message' : 'messages'}
          </h2>
          <MessageThread
            messages={messages}
            showItems
            empty="Nothing said yet. The first message is usually the hardest."
          />
        </section>
      )}
    </main>
  )
}
