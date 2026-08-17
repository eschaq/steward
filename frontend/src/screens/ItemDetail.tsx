import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  ApiError,
  claimItem,
  fetchItem,
  fetchItemClaims,
  fetchItemMessages,
  fetchMe,
  advanceDisposition,
  clarifyItem,
  withdrawClaim,
  decideDisposition,
  removeItem,
  fetchItemDisposition,
  requestListing,
  uploadItemPhoto,
} from '../api'
import { useAuth } from '../auth'
import { AnswerSteward } from '../components/AnswerSteward'
import { Claimants } from '../components/Claimants'
import { Disposition } from '../components/Disposition'
import { MessageThread } from '../components/MessageThread'
import { StatusChip } from '../components/StatusChip'
import { StewardLockup } from '../components/StewardMark'
import { estateId } from '../firebase'
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
  const [advancing, setAdvancing] = useState(false)
  const [withdrawing, setWithdrawing] = useState(false)
  const [answering, setAnswering] = useState(false)
  const [answerOutcome, setAnswerOutcome] = useState<string | null>(null)
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
        fetchMe(estateId()),
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

  async function onAnswer(text: string) {
    setProblem(null)
    setAnswerOutcome(null)
    setAnswering(true)
    try {
      const result = await clarifyItem(itemId, text)
      setItem(result.item)
      // Append rather than refetch: the server already returned both new
      // messages with their author names resolved, in order.
      setMessages((current) => [...(current ?? []), ...result.messages])
      setAnswerOutcome(
        result.failed
          ? "Steward couldn't take a second look just now — what you said is saved, and the item is unchanged."
          : result.cleared
            ? `Steward has it down as ${result.item.ai_category} now.`
            : "Steward still isn't sure what this is, so it's staying here. What you said is saved with it.",
      )
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't send that: ${error}`,
      )
    } finally {
      setAnswering(false)
    }
  }

  async function onWithdraw() {
    setProblem(null)
    setWithdrawing(true)
    try {
      await withdrawClaim(itemId)
      // Both change: the list loses your row, and the status may drop from
      // contested back to claimed — or to unclaimed if you were the only one.
      // Refetch rather than compute it here; the server owns that rule.
      const [fetched, asked] = await Promise.all([
        fetchItem(itemId),
        fetchItemClaims(itemId),
      ])
      setItem(fetched)
      setClaims(asked.claims)
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't take that back: ${error}`,
      )
    } finally {
      setWithdrawing(false)
    }
  }

  async function onAdvance() {
    setProblem(null)
    setAdvancing(true)
    try {
      setDisposition(await advanceDisposition(itemId))
      // The item's status moves to routed on the first step, and the placard
      // and the chip both read from the item — so refetch rather than guess.
      setItem(await fetchItem(itemId))
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't note that: ${error}`,
      )
    } finally {
      setAdvancing(false)
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
  // Your own claim, if you have one. `is_you` is resolved server-side, so this
  // does not depend on the client knowing its own uid.
  const yours = claims?.find((claim) => claim.is_you) ?? null

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

              {/* Already asked: say so, rather than leaving a live form that
                  quietly files a second claim for the same person. The data
                  model allows repeat claims on purpose — a second one is a real
                  event — but a form that looks untouched is not someone
                  deciding to ask twice, it is someone who thinks the first
                  click failed. */}
              {claimable && yours && (
                <div className="claim claim--yours">
                  <p className="claim__already">You've asked for this one.</p>
                  {yours.comment ? (
                    <p className="claim__yours-comment">“{yours.comment}”</p>
                  ) : (
                    <p className="claim__yours-silent">
                      You asked without saying why, which is allowed.
                    </p>
                  )}
                  <p className="claim__yours-note">
                    Want to say something different? Take your name back off
                    below, then ask again — or just add to the conversation
                    underneath.
                  </p>
                </div>
              )}

              {claimable && !yours && (
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

          <Claimants
            claims={claims ?? []}
            onWithdraw={onWithdraw}
            withdrawing={withdrawing}
          />

          <Disposition
            decided={disposition}
            canDecide={me?.role === 'executor' && item.status === 'resolved'}
            onDecide={onDecideDisposition}
            working={deciding}
            onAdvance={me?.role === 'executor' ? onAdvance : undefined}
            advancing={advancing}
          />

          {/* Only while the agent is actually waiting. Once the item has been
              placed there is nothing outstanding to answer, and the ordinary
              feed is the place for anything else. */}
          {item.status === 'needs_clarification' && (
            <AnswerSteward onAnswer={onAnswer} working={answering} />
          )}

          {/* Outside the box on purpose. A successful answer moves the item out
              of needs_clarification, which unmounts the box — and a
              confirmation that disappears at the moment it is earned is worse
              than none. */}
          {answerOutcome && (
            <p className="answer-outcome" role="status">
              {answerOutcome}
            </p>
          )}

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
