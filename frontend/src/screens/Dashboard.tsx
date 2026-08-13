import { useCallback, useEffect, useMemo, useState } from 'react'

import { ApiError, fetchEstateItems } from '../api'
import { useAuth } from '../auth'
import { ESTATE_ID } from '../firebase'
import { ItemCard } from '../components/ItemCard'
import { StatusFilters, type Filter } from '../components/StatusFilters'
import { ITEM_STATUSES, STATUS_LABEL, type Item, type ItemStatus } from '../types'

function emptyCounts(): Record<ItemStatus, number> {
  return Object.fromEntries(ITEM_STATUSES.map((s) => [s, 0])) as Record<ItemStatus, number>
}

export function Dashboard() {
  const { user, leave } = useAuth()
  const [items, setItems] = useState<Item[] | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')

  const load = useCallback(async () => {
    setProblem(null)
    try {
      const body = await fetchEstateItems(ESTATE_ID)
      setItems(body.items)
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

  return (
    <>
      <header className="app-bar">
        <div className="app-bar__inner">
          <span className="app-bar__brand">Steward</span>
          <div className="app-bar__who">
            <span className="app-bar__email label-md">{user?.email}</span>
            <button className="button button--quiet" type="button" onClick={() => void leave()}>
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="page">
        <h1 className="headline-lg">Inventory</h1>
        <p className="muted body-md" style={{ marginTop: 4 }}>
          {items === null
            ? 'Looking through the estate…'
            : `${items.length} ${items.length === 1 ? 'belonging' : 'belongings'} in this estate. Take your time.`}
        </p>

        <StatusFilters
          active={filter}
          counts={counts}
          total={items?.length ?? 0}
          onChange={setFilter}
        />

        {problem && (
          <p className="notice notice--problem" role="alert">
            {problem}{' '}
            <button
              className="button button--quiet"
              type="button"
              style={{ marginLeft: 8 }}
              onClick={() => void load()}
            >
              Try again
            </button>
          </p>
        )}

        {!problem && items === null && <p className="notice">Loading the inventory…</p>}

        {!problem && items !== null && shown.length === 0 && (
          <div className="empty">
            <p className="body-lg" style={{ margin: 0 }}>
              {items.length === 0
                ? 'Nothing catalogued in this estate yet.'
                : `Nothing is ${STATUS_LABEL[filter as ItemStatus].toLowerCase()} right now.`}
            </p>
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
    </>
  )
}
