import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, fetchMe, fetchReview, resolveItem } from '../api'
import { useAuth } from '../auth'
import { EstateNav } from '../components/EstateNav'
import { StatusChip } from '../components/StatusChip'
import { ESTATE_ID } from '../firebase'
import {
  REVIEW_ORDER,
  RESOLUTION_LABEL,
  isListedStatus,
  whereItGoes,
  type ItemStatus,
  type Me,
  type ResolutionType,
  type ReviewRow,
} from '../types'

function titleCase(value: string): string {
  return value.replace(/\b[a-z]/g, (c) => c.toUpperCase())
}

/** The executor's bulk view: every item on one page, grouped by what needs
 * doing.
 *
 * Where the inline action stops, and why:
 *
 *   A **claimed** item has exactly one person's name on it. There is nothing to
 *   weigh — the executor either agrees or doesn't — so it can be settled from
 *   the row in one click, and the row says whose name it is.
 *
 *   A **contested** item goes to the full screen instead. Settling that from a
 *   table would mean deciding between two people without reading why either
 *   wants it, or what Steward suggested. Speed is the wrong thing to optimise
 *   at that moment; this table exists to clear the uncontroversial so there is
 *   time for the rest.
 */
export function Review() {
  const { user, leave } = useAuth()
  const [me, setMe] = useState<Me | null>(null)
  const [rows, setRows] = useState<ReviewRow[] | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(async () => {
    setProblem(null)
    try {
      const standing = await fetchMe(ESTATE_ID)
      setMe(standing)
      if (standing.role) setRows((await fetchReview(ESTATE_ID)).rows)
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't load the review: ${error}`,
      )
    } finally {
      setLoaded(true)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const grouped = useMemo(() => {
    const buckets = new Map<ItemStatus, ReviewRow[]>()
    for (const status of REVIEW_ORDER) buckets.set(status, [])
    for (const row of rows ?? []) {
      if (isListedStatus(row.status)) buckets.get(row.status)?.push(row)
    }
    return [...buckets.entries()].filter(([, group]) => group.length > 0)
  }, [rows])

  async function assignToSoleClaimant(row: ReviewRow) {
    if (!row.sole_claimant_id) return
    setProblem(null)
    setBusy(row.id)
    try {
      await resolveItem(row.id, {
        resolution_type: 'assigned_to_claimant',
        resolved_to_user_id: row.sole_claimant_id,
        notes: `Assigned to ${row.sole_claimant_name} from the review table.`,
      })
      // Refetch the whole table: resolving moves the row between groups and
      // changes the counts above it, neither of which the client should guess.
      setRows((await fetchReview(ESTATE_ID)).rows)
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't settle that: ${error}`,
      )
    } finally {
      setBusy(null)
    }
  }

  const isExecutor = me?.role === 'executor'

  return (
    <main className="page">
      <header className="hero hero--slim">
        <div className="hero__top">
          <EstateNav active="review" />
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
          <h1 className="display hero__title">Review</h1>
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

      {!loaded && <p className="notice">Gathering the estate…</p>}

      {loaded && !isExecutor && (
        <div className="notice" style={{ marginTop: 18 }}>
          Only the executor works through the estate this way. Everything here is
          on <Link to="/">the inventory</Link> too, an item at a time.
        </div>
      )}

      {loaded && isExecutor && rows !== null && (
        <>
          <p className="review__intro">
            Everything in the estate, with what needs a decision first. Take it at
            whatever pace suits.
          </p>

          {grouped.map(([status, group]) => {
            // Only a settled or routed item has anywhere to go yet, so the
            // column appears where it means something rather than sitting empty
            // above every other group.
            const showsDestination = status === 'resolved' || status === 'routed'
            return (
            <section className="review__group" key={status}>
              <h2 className="review__heading">
                <StatusChip status={status} />
                <span className="review__count">
                  {group.length} {group.length === 1 ? 'item' : 'items'}
                </span>
              </h2>

              <table className="review">
                <thead>
                  <tr>
                    <th scope="col">Item</th>
                    <th scope="col">Asked for by</th>
                    <th scope="col">Suggested</th>
                    <th scope="col">{showsDestination ? 'Decided' : ''}</th>
                    {showsDestination && <th scope="col">Where it goes</th>}
                  </tr>
                </thead>
                <tbody>
                  {group.map((row) => (
                    <tr key={row.id}>
                      <th scope="row">
                        <span className="review__item">
                          {row.photo_url ? (
                            <img
                              className="review__thumb"
                              src={row.photo_url}
                              // Decorative: the item's name is the very next
                              // thing in this cell, so alt text here would make
                              // a screen reader announce it twice.
                              alt=""
                              loading="lazy"
                            />
                          ) : (
                            <span className="review__thumb--none" aria-hidden="true" />
                          )}
                          <span>
                            <Link to={`/items/${row.id}`} className="review__name">
                              {titleCase(row.ai_category)}
                            </Link>
                            {row.ai_est_era_or_brand && (
                              <span className="review__era">{row.ai_est_era_or_brand}</span>
                            )}
                          </span>
                        </span>
                      </th>

                      <td>
                        {row.claimant_count === 0 ? (
                          <span className="review__quiet">Nobody yet</span>
                        ) : row.sole_claimant_name ? (
                          row.sole_claimant_name
                        ) : (
                          `${row.claimant_count} people`
                        )}
                      </td>

                      <td>
                        {row.suggested_disposition === 'uncertain' ? (
                          <span className="review__quiet">No suggestion yet</span>
                        ) : (
                          titleCase(row.suggested_disposition)
                        )}
                        <span className="review__confidence">
                          {Math.round(row.ai_classification_confidence * 100)}% sure
                        </span>
                      </td>

                      <td className="review__action">
                        {row.decided_type && (
                          <span className="review__decided">
                            {RESOLUTION_LABEL[row.decided_type as ResolutionType] ??
                              row.decided_type}
                            {row.decided_to_name ? ` — ${row.decided_to_name}` : ''}
                          </span>
                        )}

                        {/* One name on it: settle from here. */}
                        {row.status === 'claimed' && row.sole_claimant_id && (
                          <button
                            className="button button--sage"
                            type="button"
                            disabled={busy === row.id}
                            onClick={() => void assignToSoleClaimant(row)}
                          >
                            {busy === row.id
                              ? 'Settling…'
                              : `It goes to ${row.sole_claimant_name}`}
                          </button>
                        )}

                        {/* More than one name: read it properly first. */}
                        {row.status === 'contested' && (
                          <Link className="button button--sage" to={`/items/${row.id}/resolve`}>
                            Talk it through →
                          </Link>
                        )}

                        {row.status === 'needs_clarification' && (
                          <Link className="review__link" to={`/items/${row.id}`}>
                            Steward asked something →
                          </Link>
                        )}
                      </td>

                      {showsDestination && (
                        <td>
                          {row.disposition ? (
                            <span className="review__destination">
                              {whereItGoes(row.disposition)}
                            </span>
                          ) : (
                            /* Not an empty cell: settled and undecided is the
                               one place left where this table has something to
                               ask of the executor. */
                            <Link className="review__link" to={`/items/${row.id}`}>
                              Where does it go? →
                            </Link>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
            )
          })}
        </>
      )}
    </main>
  )
}
