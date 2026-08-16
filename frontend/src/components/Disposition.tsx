import { useState } from 'react'

import {
  ADVANCE_ACTION,
  CHANNEL_LABEL,
  CHANNEL_SHORT,
  DISPOSITION_PROGRESS,
  DISPOSITION_CHOICES,
  DISPOSITION_HELP,
  DISPOSITION_LABEL,
  PLATFORM_LABEL,
  type DispositionChoice,
  type DispositionDetail,
} from '../types'

/** Where a settled item goes next, and — if it is being sold — where it will be
 * listed.
 *
 * Two states, the same pattern the resolution screen uses: controls until a
 * decision exists, then a plain statement of what was decided. Choosing "sell"
 * asks Steward where to list it in the same action, because a sell decision
 * without a channel is a half-finished thought.
 */
/** Whole dollars, because a suggested asking price with cents on it pretends to
 * a precision nobody has. */
function money(amount: number): string {
  return amount.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: amount % 1 === 0 ? 0 : 2,
  })
}

export function Disposition({
  decided,
  canDecide,
  onDecide,
  working,
  onAdvance,
  advancing,
}: {
  decided: DispositionDetail | null
  canDecide: boolean
  onDecide: (choice: DispositionChoice) => void | Promise<void>
  /** The choice currently being recorded — "sell" also waits on Steward. */
  working: DispositionChoice | null
  /** Mark the next thing that actually happened. Executor only. */
  onAdvance?: () => void | Promise<void>
  advancing?: boolean
}) {
  const [chosen, setChosen] = useState<DispositionChoice | null>(null)

  if (decided) {
    const listing = decided.listing
    const done = decided.status === 'completed'
    // Once it has actually gone, the heading says so. "Being given away" over
    // "Given away" is both redundant and, by then, untrue.
    const heading = done
      ? (CHANNEL_SHORT[decided.channel] ?? decided.channel)
      : (CHANNEL_LABEL[decided.channel] ?? decided.channel)
    const when = decided.completed_at
      ? new Date(decided.completed_at).toLocaleDateString(undefined, {
          month: 'long',
          day: 'numeric',
          year: 'numeric',
        })
      : null
    return (
      <section className="disposition disposition--done">
        <h2 className="eyebrow">Where it goes</h2>
        <p className="disposition__what">{heading}</p>

        {/* Where it has actually got to, in the words of the thing that
            happened — never the raw pending/in_progress/completed. Once it is
            done the heading carries that, so this is just the date. */}
        <p className="disposition__progress">
          {done
            ? (when ?? 'Done')
            : (DISPOSITION_PROGRESS[decided.channel]?.[decided.status] ?? decided.status)}
        </p>

        {onAdvance && decided.status !== 'completed' && (
          <button
            className="button button--sage disposition__advance"
            type="button"
            disabled={advancing}
            onClick={() => void onAdvance()}
          >
            {advancing
              ? 'Noting it…'
              : decided.status === 'pending'
                ? (ADVANCE_ACTION[decided.channel]?.next ?? 'Mark the next step')
                : (ADVANCE_ACTION[decided.channel]?.last ?? 'Mark it done')}
          </button>
        )}

        {listing && (
          <div className="listing">
            <div className="listing__head">
              <span className="eyebrow">Steward suggests</span>
              <span className="tag listing__platform">
                {PLATFORM_LABEL[listing.platform] ?? listing.platform}
              </span>
            </div>
            <p className="listing__reason">{listing.platform_recommendation_reason}</p>

            {listing.suggested_price !== null && (
              <p className="listing__price">
                <span className="listing__amount">{money(listing.suggested_price)}</span>
                <span className="listing__price-note">
                  A starting point, not an appraisal — change it to whatever seems
                  right.
                </span>
              </p>
            )}

            {(listing.listing_draft_title || listing.listing_draft_description) && (
              <div className="listing__draft">
                <span className="eyebrow">The listing, if you want it</span>
                {listing.listing_draft_title && (
                  <h3 className="listing__draft-title">{listing.listing_draft_title}</h3>
                )}
                {listing.listing_draft_description && (
                  <p className="listing__draft-body">{listing.listing_draft_description}</p>
                )}
                <p className="listing__draft-note">
                  Yours to change before it goes anywhere. Steward has said what's
                  worn or missing — that stays in.
                </p>
              </div>
            )}

            {/* An honest gap, not an empty field: the model was asked for these
                and something came back unusable. */}
            {listing.suggested_price === null && !listing.listing_draft_title && (
              <p className="listing__pending">
                No price or wording came back for this one — worth writing it
                yourself.
              </p>
            )}
          </div>
        )}
      </section>
    )
  }

  if (!canDecide) return null

  return (
    <section className="disposition">
      <h2 className="eyebrow">Where does it go?</h2>
      <p className="disposition__intro">
        It's settled who it belongs to. There's no hurry on this next part.
      </p>

      <div className="disposition__choices">
        {DISPOSITION_CHOICES.map((choice) => (
          <button
            key={choice}
            type="button"
            className={`disposition__choice${chosen === choice ? ' disposition__choice--on' : ''}`}
            disabled={working !== null}
            onClick={() => {
              setChosen(choice)
              void onDecide(choice)
            }}
          >
            <span className="disposition__choice-name">
              {working === choice
                ? choice === 'sell'
                  ? 'Asking Steward where…'
                  : 'Recording…'
                : DISPOSITION_LABEL[choice]}
            </span>
            <span className="disposition__choice-help">{DISPOSITION_HELP[choice]}</span>
          </button>
        ))}
      </div>
    </section>
  )
}
