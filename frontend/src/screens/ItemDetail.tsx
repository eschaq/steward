import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  ApiError,
  claimItem,
  fetchItem,
  fetchItemClaims,
  fetchItemMessages,
  fetchMe,
  decideDisposition,
  removeItem,
  fetchItemDisposition,
  requestListing,
  uploadItemPhoto,
} from '../api'
import { useAuth } from '../auth'
import { Claimants } from '../components/Claimants'
import { Disposition } from '../components/Disposition'
import { MessageThread } from '../components/MessageThread'
import { StatusChip } from '../components/StatusChip'
import { StewardLockup } from '../components/StewardMark'
import { ESTATE_ID } from '../firebase'
import {
  STATUS_MEANING,
  firstPhoto,
  photoAlt,
  isClaimable,
  isItemStatus,
  type Claimant,
  type DispositionChoice,
  type DispositionDetail,
  type Item,
  type Me,
  type Message,
} from '../types'

function titleCase(value: string): string {
  return value.replace(/\b[a-z]/g, (c) => c.toUpperCase())
}

export function ItemDetail() {
  const { itemId = '' } = useParams()
  const { user, leave } = useAuth()

  const [item, setItem] = useState<Item | null>(null)
  const [messages, setMessages] = useState<Message[] | null>(null)
  const [claims, setClaims] = useState<Claimant[] | null>(null)
  const [me, setMe] = useState<Me | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [claiming, setClaiming] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [disposition, setDisposition] = useState<DispositionDetail | null>(null)
  const [deciding, setDeciding] = useState<DispositionChoice | null>(null)
  const [asking, setAsking] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [comment, setComment] = useState('')

  const load = useCallback(async () => {
    setProblem(null)
    try {
      // Both together: a status without its thread is half the story, and the
      // thread is what explains the status.
      const [fetched, thread, asked, standing, headed] = await Promise.all([
        fetchItem(itemId),
        fetchItemMessages(itemId),
        fetchItemClaims(itemId),
        fetchMe(ESTATE_ID),
        fetchItemDisposition(itemId),
      ])
      setItem(fetched)
      setMessages(thread.messages)
      setClaims(asked.claims)
      setMe(standing)
      setDisposition(headed)
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't load this item: ${error}`,
      )
    }
  }, [itemId])

  useEffect(() => {
    void load()
  }, [load])

  async function onClaim() {
    setProblem(null)
    setClaiming(true)
    try {
      await claimItem(itemId, comment)
      setComment('')
      // Refetch rather than patching local state: claiming can flip the item to
      // contested and make the agent post a mediation message, and neither of
      // those is something the client can predict.
      await load()
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't record that claim: ${error}`,
      )
    } finally {
      setClaiming(false)
    }
  }

  async function onPhoto(file: File | undefined) {
    if (!file) return
    setProblem(null)
    setUploading(true)
    try {
      // The endpoint returns the updated item, so the photo appears without a
      // refetch — and the placard expands from its slim band to the full
      // two-column treatment on the same render.
      setItem(await uploadItemPhoto(itemId, file))
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't add that photo: ${error}`,
      )
    } finally {
      setUploading(false)
    }
  }

  async function onDecideDisposition(choice: DispositionChoice) {
    setProblem(null)
    setDeciding(choice)
    try {
      await decideDisposition(itemId, choice)
      // A sell decision without a channel is a half-finished thought, so the
      // recommendation is part of the same action rather than a second button
      // the executor has to know to press.
      if (choice === 'sell') await requestListing(itemId)
      setDisposition(await fetchItemDisposition(itemId))
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't record that: ${error}`,
      )
    } finally {
      setDeciding(null)
    }
  }

  async function onRemove() {
    setProblem(null)
    setRemoving(true)
    try {
      setItem(await removeItem(itemId))
      setAsking(false)
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't take that off: ${error}`,
      )
    } finally {
      setRemoving(false)
    }
  }

  // The mediation post, if there is one — the agent's answer to a contested
  // item, which is the whole behaviour made visible.
  const mediationId = useMemo(() => {
    if (item?.status !== 'contested') return null
    return messages?.find((m) => m.is_agent && m.id.startsWith('agent-mediate__'))?.id ?? null
  }, [item?.status, messages])

  const photo = firstPhoto(item?.photo_urls)
  const usablePhoto = Boolean(photo)
  const claimable = Boolean(item && isClaimable(item.status))

  return (
    <main className="page">
      <header className="hero hero--slim">
        <div className="hero__top">
          <Link to="/" className="hero__back">
            <StewardLockup size={24} color="var(--on-ink)" />
          </Link>
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
        <Link to="/" className="hero__crumb">
          ← Back to the inventory
        </Link>
      </header>

      {problem && (
        <p className="notice notice--problem" role="alert">
          <span>{problem}</span>
          <button className="button button--sage" type="button" onClick={() => void load()}>
            Try again
          </button>
        </p>
      )}

      {!problem && item === null && <p className="notice">Fetching this one…</p>}

      {item && (
        <>
          <article className={`placard${usablePhoto ? '' : ' placard--no-photo'}`}>
            <div className={`placard__photo${usablePhoto ? '' : ' card__photo--empty'}`}>
              {usablePhoto ? (
                <img src={photo} alt={photoAlt(item)} />
              ) : me?.role === 'executor' ? (
                <label className="photo-add">
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/heic"
                    onChange={(e) => void onPhoto(e.target.files?.[0])}
                    disabled={uploading}
                  />
                  <span className="photo-add__label">
                    {uploading ? 'Adding the photo…' : 'No photo yet — add one'}
                  </span>
                </label>
              ) : (
                <span>No photo yet</span>
              )}
            </div>

            <div className="placard__body">
              <div className="placard__marks">
                <StatusChip status={item.status} />
                {item.ai_est_era_or_brand && (
                  <span className="tag tag--routed">{item.ai_est_era_or_brand}</span>
                )}
              </div>

              <h1 className="placard__title">{titleCase(item.ai_category)}</h1>

              <p className="placard__notes">{item.ai_condition_notes}</p>

              <dl className="placard__facts">
                <div>
                  <dt>Where it stands</dt>
                  <dd>
                    {isItemStatus(item.status)
                      ? STATUS_MEANING[item.status]
                      : item.status}
                  </dd>
                </div>
                <div>
                  <dt>Suggested</dt>
                  <dd>
                    {item.suggested_disposition === 'uncertain'
                      ? 'No suggestion yet — Steward has nothing similar to go on.'
                      : `Leaning ${item.suggested_disposition}.`}
                  </dd>
                </div>
                <div>
                  <dt>How sure Steward is</dt>
                  <dd>
                    {Math.round(item.ai_classification_confidence * 100)}% sure it read
                    this one right.
                  </dd>
                </div>
              </dl>

              {/* Only the executor can settle it, so only they are offered the
                  way through. The route checks again on arrival, and the
                  backend checks again on write. */}
              {me?.role === 'executor' &&
                (item.status === 'contested' || item.status === 'claimed') && (
                  <div className="settle">
                    <Link className="button button--sage" to={`/items/${itemId}/resolve`}>
                      Record how this was settled →
                    </Link>
                  </div>
                )}

              {claimable && (
                <div className="claim">
                  <label htmlFor="claim-comment" className="claim__label">
                    Say why, if you'd like to. Nobody has to.
                  </label>
                  <textarea
                    id="claim-comment"
                    className="claim__comment"
                    rows={2}
                    placeholder="It sat in the hall my whole childhood…"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                  />
                  <button
                    className="button button--primary"
                    type="button"
                    onClick={() => void onClaim()}
                    disabled={claiming}
                  >
                    {claiming ? 'Putting your name down…' : 'Put my name down for this'}
                  </button>
                </div>
              )}
            </div>
          </article>

          <Claimants claims={claims ?? []} />

          <Disposition
            decided={disposition}
            canDecide={me?.role === 'executor' && item.status === 'resolved'}
            onDecide={onDecideDisposition}
            working={deciding}
          />

          <section className="thread-section">
            <h2 className="eyebrow">About this one</h2>
            <MessageThread messages={messages ?? []} prominentId={mediationId} />
          </section>

          {/* Last on the page on purpose. Taking something off the list is not
              what anyone came here to do, so it doesn't sit above the thing
              they did come for. */}
          {me?.role === 'executor' && (
            <section className="remove">
              {item.status === 'removed' ? (
                <p className="remove__done">
                  This one is off the list. Everything said about it is still
                  here, and this page will keep working — it just won't show up
                  in the inventory or the review table.
                </p>
              ) : asking ? (
                <div className="remove__ask">
                  <p className="remove__question">
                    Take this off the list? You can still find it if you need to
                    — nothing gets thrown away.
                  </p>
                  <div className="remove__actions">
                    <button
                      className="button button--sage"
                      type="button"
                      onClick={() => void onRemove()}
                      disabled={removing}
                    >
                      {removing ? 'Taking it off…' : 'Yes, take it off'}
                    </button>
                    <button
                      className="button button--quiet"
                      type="button"
                      onClick={() => setAsking(false)}
                      disabled={removing}
                    >
                      Leave it
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  className="remove__start"
                  type="button"
                  onClick={() => setAsking(true)}
                >
                  Take this off the list
                </button>
              )}
            </section>
          )}
        </>
      )}
    </main>
  )
}
