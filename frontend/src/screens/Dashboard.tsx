import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError, fetchEstateItems, fetchMe } from '../api'
import { useAuth } from '../auth'
import { estateId } from '../firebase'
import { AddItem } from '../components/AddItem'
import { ItemCard } from '../components/ItemCard'
import { StatusFilters, type Filter } from '../components/StatusFilters'
import { EstateNav } from '../components/EstateNav'
import {
  ITEM_STATUSES,
  STATUS_LABEL,
  type Item,
  type ItemStatus,
  type Me,
} from '../types'

function emptyCounts(): Record<ItemStatus, number> {
  return Object.fromEntries(ITEM_STATUSES.map((s) => [s, 0])) as Record<ItemStatus, number>
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

export function Dashboard() {
  const { user, leave } = useAuth()
  const navigate = useNavigate()
  const [items, setItems] = useState<Item[] | null>(null)
  const [me, setMe] = useState<Me | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')

  const load = useCallback(async () => {
    setProblem(null)
    try {
      const [body, standing] = await Promise.all([
        fetchEstateItems(estateId()),
        fetchMe(estateId()),
      ])
      setItems(body.items)
      setMe(standing)
    } catch (error) {
      // Say what went wrong rather than showing an empty grid that looks like
      // an estate with nothing in it.
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't load the inventory: ${error}`,
      )
      setItems(null)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const counts = useMemo(() => {
    const tally = emptyCounts()
    for (const item of items ?? []) {
      if (item.status in tally) tally[item.status as ItemStatus] += 1
    }
    return tally
  }, [items])

  const shown = useMemo(
    () => (filter === 'all' ? (items ?? []) : (items ?? []).filter((i) => i.status === filter)),
    [items, filter],
  )

  // Straight to the new item rather than back to a grid of thirty-nine cards
  // to hunt through. What Steward made of the photograph is the thing the
  // executor just asked a question about, so it should be the thing they see.
  function added(item: Item) {
    navigate(`/items/${item.id}`)
  }

  const total = items?.length ?? 0
  // A ledger, not a score: how many things are where, with no target to hit.
  //
  // "Settled" means exactly `resolved`, the same as the status chip and the
  // filter tab. It used to fold in `routed` as well, so this card and the tab
  // beneath it disagreed on the same screen (14 against 13). `Settled` and
  // `On its way` are two distinct words this app teaches people — a card using
  // one of them to mean both is the bug, not the tab.
  const settled = counts.resolved

  // A block with nothing in it drops to the quiet tone. A big clay-red 0 would
  // be shouting about an absence of anything to shout about.
  const tone = (count: number, colour: string) =>
    `ledger__block ledger__block--${count === 0 ? 'quiet' : colour}`

  return (
    <main className="page">
      <header className="hero">
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

        <div>
          <div className="eyebrow eyebrow--on-ink">{me?.estate_name ?? estateId()}</div>
          <h1 className="display hero__title">Inventory</h1>
        </div>

        {items !== null && (
          <div className="hero__marks">
            <span className="tag tag--on-ink">{plural(total, 'belonging', 'belongings')}</span>
            <span className="tag tag--on-ink">
              {plural(counts.unclaimed, 'unspoken for', 'unspoken for')}
            </span>
            <span className="tag tag--on-ink">
              {plural(counts.claimed, 'spoken for', 'spoken for')}
            </span>
          </div>
        )}
      </header>

      {items !== null && me?.role === 'executor' && <AddItem onAdded={added} />}

      {items !== null && (
        <div className="ledger">
          <div className={tone(settled, 'sage')}>
            <div className="ledger__label">Settled</div>
            <div className="ledger__value">
              <span className="ledger__number">{settled}</span>
              <span className="ledger__unit">
                {settled === 1 ? 'item' : 'items'} decided
              </span>
            </div>
          </div>

          <div className={tone(counts.contested, 'clay')}>
            <div className="ledger__label">Needs a talk</div>
            <div className="ledger__value">
              <span className="ledger__number">{counts.contested}</span>
              <span className="ledger__unit">
                {counts.contested === 1 ? 'item' : 'items'} contested
              </span>
            </div>
          </div>

          <div className={tone(counts.needs_clarification, 'archive')}>
            <div className="ledger__label">Needs a look</div>
            <div className="ledger__value">
              <span className="ledger__number">{counts.needs_clarification}</span>
              <span className="ledger__unit">Steward has asked</span>
            </div>
          </div>
        </div>
      )}

      <StatusFilters active={filter} counts={counts} total={total} onChange={setFilter} />

      {problem && (
        <p className="notice notice--problem" role="alert">
          <span>{problem}</span>
          <button className="button button--sage" type="button" onClick={() => void load()}>
            Try again
          </button>
        </p>
      )}

      {!problem && items === null && (
        <p className="notice">Looking through the estate…</p>
      )}

      {!problem && items !== null && shown.length === 0 && (
        <div className="empty">
          {total === 0
            ? 'Nothing catalogued in this estate yet.'
            : /* Quoted, not inlined: "Nothing is needs a talk right now" is what
                 you get when a label is dropped into a sentence that assumes an
                 adjective. */
              `Nothing is marked “${STATUS_LABEL[filter as ItemStatus]}” right now.`}
        </div>
      )}

      {shown.length > 0 && (
        <div className="grid">
          {shown.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </main>
  )
}
