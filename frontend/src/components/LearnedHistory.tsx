import { useState } from 'react'

import { DISPOSITION_LABEL, type OverrideLog } from '../types'

/** Indexed by whatever the server sends, not just the three we expect — an
 * unrecognised channel should render as itself rather than blank. */
const label = (key: string): string =>
  (DISPOSITION_LABEL as Record<string, string>)[key] ?? key

function when(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

/** Three forms, because one doesn't fit three sentences.
 *
 * PERFECT follows "You've" — "You've given away 3 of 4".
 * PAST stands alone — "You gave away the dinnerware".
 * LEANING follows "leans" — "leans towards giving it away", rather than the
 * button's imperative label, which reads as "leans give it away".
 */
const PERFECT: Record<string, string> = {
  donate: 'given away',
  sell: 'sold',
  discard: 'let go',
}

const PAST: Record<string, string> = {
  donate: 'gave away',
  sell: 'sold',
  discard: 'let go of',
}

const LEANING: Record<string, string> = {
  donate: 'giving it away',
  sell: 'selling',
  discard: 'letting it go',
}

function plural(category: string, n: number): string {
  if (n === 1) return `one ${category}`
  return `${n} ${category}${/s$/.test(category) ? '' : 's'}`
}

/** What this estate has decided, and the habit Steward reads from it.
 *
 * The adaptive loop is the product's whole argument, and until now it ran
 * where nobody could see it: the agent would say "this estate has donated 3 of
 * 4 armchairs" on an item page and the family had no way to check whether that
 * was true. This is that sentence's evidence.
 *
 * Patterns first, entries second. A raw list of ten rows is a log; the tally is
 * the thing that makes someone say "oh — it's learning from *us*".
 *
 * The arithmetic is the server's, which is the server's copy of what
 * `overrides.suggest_disposition()` computes — so this panel and the agent can
 * never tell two different stories about the same family.
 */
export function LearnedHistory({ log }: { log: OverrideLog | null }) {
  const [showAll, setShowAll] = useState(false)

  if (!log) return null

  if (log.count === 0) {
    return (
      <section className="learned">
        <h2 className="eyebrow">What Steward has learned</h2>
        <p className="learned__empty">
          Nothing yet. Once you've decided where a few things go, Steward starts
          noticing what this family tends to do — and says so when it suggests
          something.
        </p>
      </section>
    )
  }

  // A category decided once is a fact, not a habit. Saying "leaning donate"
  // off a single decision would overclaim, so those sit in the quieter list.
  const habits = log.patterns.filter((p) => p.total > 1)
  const singles = log.patterns.filter((p) => p.total === 1)
  const entries = showAll ? log.entries : log.entries.slice(-6)

  return (
    <section className="learned">
      <h2 className="eyebrow">What Steward has learned</h2>
      <p className="learned__intro">
        Every decision you record teaches it something about this family in
        particular. Here's what it's noticed so far — it's the same arithmetic
        behind the suggestions on each item.
      </p>

      {habits.length > 0 && (
        <ul className="learned__patterns">
          {habits.map((p) => (
            <li
              className={`learned__pattern${p.split ? ' learned__pattern--split' : ''}`}
              key={p.category}
            >
              {p.split ? (
                <>
                  <p className="learned__claim">
                    You're evenly split on {p.category}.
                  </p>
                  <p className="learned__detail">
                    {Object.entries(p.counts)
                      .map(([k, n]) => `${n} ${PERFECT[k] ?? k}`)
                      .join(', ')}
                    {' — '}so Steward won't guess. It says so on the item, rather
                    than picking a side.
                  </p>
                </>
              ) : (
                <>
                  <p className="learned__claim">
                    You've {PERFECT[p.leaning ?? ''] ?? p.leaning}{' '}
                    {p.leaning_count === p.total
                      ? plural(p.category, p.total)
                      : `${p.leaning_count} of ${plural(p.category, p.total)}`}
                    .
                  </p>
                  <p className="learned__detail">
                    So Steward now leans towards{' '}
                    <strong>{LEANING[p.leaning ?? ''] ?? label(p.leaning ?? '')}</strong>{' '}
                    for the next one.
                  </p>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {singles.length > 0 && (
        <p className="learned__singles">
          One decision each so far on {singles.map((p) => p.category).join(', ')}
          {' '}— not enough to be a habit yet.
        </p>
      )}

      <details
        className="learned__entries"
        open={showAll}
        onToggle={(e) => setShowAll((e.target as HTMLDetailsElement).open)}
      >
        <summary className="learned__summary">
          {log.count} {log.count === 1 ? 'decision' : 'decisions'} in full
        </summary>
        <ul className="learned__list">
          {entries.map((e) => (
            <li className="learned__entry" key={`${e.item_id}-${e.created_at}`}>
              <span className="learned__entry-what">
                {/* Never "Steward suggested uncertain" — early on it genuinely
                    had no view, and saying otherwise would invent an opinion. */}
                {e.steward_had_a_view ? (
                  <>
                    Steward leaned towards{' '}
                    {LEANING[e.ai_suggested_disposition] ??
                      label(e.ai_suggested_disposition).toLowerCase()}
                    ; you {PAST[e.executor_chosen_disposition]} the{' '}
                    {e.item_category}
                    {e.agreed ? ' — agreed' : ''}
                  </>
                ) : (
                  <>
                    You {PAST[e.executor_chosen_disposition]} the {e.item_category}
                    <span className="learned__noview"> — Steward had no view yet</span>
                  </>
                )}
              </span>
              <span className="learned__entry-when">{when(e.created_at)}</span>
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}
