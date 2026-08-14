import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  ApiError,
  fetchItem,
  fetchItemClaims,
  fetchItemMessages,
  fetchItemResolution,
  fetchMe,
  resolveItem,
} from '../api'
import { useAuth } from '../auth'
import { Claimants } from '../components/Claimants'
import { EstateNav } from '../components/EstateNav'
import { MessageThread } from '../components/MessageThread'
import { StatusChip } from '../components/StatusChip'
import { ESTATE_ID } from '../firebase'
import {
  RESOLUTION_HELP,
  RESOLUTION_LABEL,
  RESOLUTION_TYPES,
  needsRecipient,
  type Claimant,
  type Item,
  type Me,
  type Message,
  type ResolutionDetail,
  type ResolutionType,
} from '../types'

function titleCase(value: string): string {
  return value.replace(/\b[a-z]/g, (c) => c.toUpperCase())
}

/** The executor's decision screen for a contested or claimed item.
 *
 * A route of its own rather than a panel inside ItemDetail. Recording a
 * resolution is a decision with consequences — it moves the item out of the
 * claim flow and makes it eligible for disposition — and a distinct URL makes
 * that a deliberate act rather than something reached by scrolling. It is also
 * a thing an executor may want to come back to, or open from a message.
 *
 * Nothing is duplicated to pay for it: the claimant list, the mediation post
 * and the status chip are the same components ItemDetail uses.
 */
export function ResolveItem() {
  const { itemId = '' } = useParams()
  const { user, leave } = useAuth()

  const [me, setMe] = useState<Me | null>(null)
  const [item, setItem] = useState<Item | null>(null)
  const [claims, setClaims] = useState<Claimant[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [resolution, setResolution] = useState<ResolutionDetail | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  const [type, setType] = useState<ResolutionType>('assigned_to_claimant')
  const [recipient, setRecipient] = useState<string>('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setProblem(null)
    try {
      const [standing, fetched, asked, thread, decided] = await Promise.all([
        fetchMe(ESTATE_ID),
        fetchItem(itemId),
        fetchItemClaims(itemId),
        fetchItemMessages(itemId),
        fetchItemResolution(itemId),
      ])
      setMe(standing)
      setItem(fetched)
      setClaims(asked.claims)
      setMessages(thread.messages)
      setResolution(decided)
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't load this item: ${error}`,
      )
    } finally {
      setLoaded(true)
    }
  }, [itemId])

  useEffect(() => {
    void load()
  }, [load])

  // Distinct people, in the order they asked. The backend will only accept a
  // recipient who actually claimed the item, so these are the only valid picks.
  const claimants = useMemo(() => {
    const seen = new Map<string, Claimant>()
    for (const claim of claims) if (!seen.has(claim.user_id)) seen.set(claim.user_id, claim)
    return [...seen.values()]
  }, [claims])

  useEffect(() => {
    if (!recipient && claimants.length > 0) setRecipient(claimants[0].user_id)
  }, [claimants, recipient])

  const mediationId = useMemo(
    () => messages.find((m) => m.is_agent && m.id.startsWith('agent-mediate__'))?.id ?? null,
    [messages],
  )
  const mediation = useMemo(
    () => messages.filter((m) => m.id === mediationId),
    [messages, mediationId],
  )

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setProblem(null)
    setSaving(true)
    try {
      await resolveItem(itemId, {
        resolution_type: type,
        resolved_to_user_id: needsRecipient(type) ? recipient : null,
        notes,
      })
      // Refetch rather than assuming: the item's status and the stored
      // resolution are both server-side consequences of this call.
      await load()
      setNotes('')
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't record that: ${error}`,
      )
    } finally {
      setSaving(false)
    }
  }

  const isExecutor = me?.role === 'executor'
  const alreadyDecided = Boolean(resolution)
  const canDecide = isExecutor && !alreadyDecided

  return (
    <div className="page">
      <header className="hero hero--slim">
        <div className="hero__top">
          <EstateNav active="inventory" />
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
        <Link to={`/items/${itemId}`} className="hero__crumb">
          ← Back to the item
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

      {!loaded && <p className="notice">Fetching this one…</p>}

      {loaded && item && (
        <>
          <div className="resolve__head">
            <div className="placard__marks">
              <StatusChip status={item.status} />
              {item.ai_est_era_or_brand && (
                <span className="tag tag--routed">{item.ai_est_era_or_brand}</span>
              )}
            </div>
            <h1 className="placard__title">{titleCase(item.ai_category)}</h1>
            <p className="placard__notes">{item.ai_condition_notes}</p>
          </div>

          {/* Steward's suggestion first, so the executor reads it before
              deciding rather than scrolling past the form to find it. */}
          {mediation.length > 0 && (
            <section className="thread-section">
              <h2 className="eyebrow">What Steward suggested</h2>
              <MessageThread messages={mediation} prominentId={mediationId} />
            </section>
          )}

          <Claimants claims={claims} />

          {!isExecutor && (
            <div className="notice" style={{ marginTop: 24 }}>
              Only the executor can record this decision. You can still say what
              you think on <Link to={`/items/${itemId}`}>the item's page</Link> —
              it all gets read.
            </div>
          )}

          {alreadyDecided && resolution && (
            <section className="decided">
              <h2 className="eyebrow">What was decided</h2>
              <p className="decided__what">
                {RESOLUTION_LABEL[resolution.resolution_type as ResolutionType] ??
                  resolution.resolution_type}
                {resolution.resolved_to_name ? ` — ${resolution.resolved_to_name}` : ''}
              </p>
              {resolution.notes && <p className="decided__notes">“{resolution.notes}”</p>}
              <p className="decided__by">
                Recorded by {resolution.resolved_by_name} on{' '}
                {new Date(resolution.resolved_at).toLocaleDateString(undefined, {
                  day: 'numeric',
                  month: 'long',
                })}
                .
              </p>
            </section>
          )}

          {canDecide && (
            <form className="resolve" onSubmit={onSubmit}>
              <h2 className="eyebrow">Record what you've decided</h2>

              <fieldset className="resolve__types">
                <legend className="resolve__legend">How is it settled?</legend>
                {RESOLUTION_TYPES.map((option) => (
                  <label
                    key={option}
                    className={`resolve__option${type === option ? ' resolve__option--on' : ''}`}
                  >
                    <input
                      type="radio"
                      name="resolution_type"
                      value={option}
                      checked={type === option}
                      onChange={() => setType(option)}
                    />
                    <span>
                      <span className="resolve__option-name">{RESOLUTION_LABEL[option]}</span>
                      <span className="resolve__option-help">{RESOLUTION_HELP[option]}</span>
                    </span>
                  </label>
                ))}
              </fieldset>

              {needsRecipient(type) && (
                <div className="field field--light">
                  <label htmlFor="recipient">Who does it go to?</label>
                  {claimants.length === 0 ? (
                    // The backend requires a recipient who claimed the item, so
                    // this combination genuinely cannot be recorded.
                    <p className="resolve__none">
                      Nobody has asked for this one, so there is no claimant to
                      assign it to. Use “Something else — your call”.
                    </p>
                  ) : (
                    <select
                      id="recipient"
                      value={recipient}
                      onChange={(e) => setRecipient(e.target.value)}
                    >
                      {claimants.map((claimant) => (
                        <option key={claimant.user_id} value={claimant.user_id}>
                          {claimant.is_you ? 'You' : claimant.claimant_name}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )}

              <div className="field field--light">
                <label htmlFor="notes">Anything worth writing down?</label>
                <textarea
                  id="notes"
                  className="claim__comment"
                  rows={3}
                  placeholder="Agreed at the kitchen table — Sarah takes it, David gets first pick of the books."
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </div>

              <button
                className="button button--primary"
                type="submit"
                disabled={saving || (needsRecipient(type) && claimants.length === 0)}
              >
                {saving ? 'Recording…' : 'Record this decision'}
              </button>
            </form>
          )}
        </>
      )}
    </div>
  )
}
