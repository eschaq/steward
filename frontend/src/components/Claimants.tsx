import { useState } from 'react'

import type { Claimant } from '../types'

function when(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

/** Who has put their name forward, and what they said about it.
 *
 * Two jobs. It gives a submitted comment somewhere to land — the claim form
 * invites a reason, and a reason that vanishes teaches people not to give one.
 * And on a contested item it is what makes the agent's mediation legible: the
 * message says "David and Sarah have both asked for this one", and without this
 * section those names appear nowhere else on the page.
 *
 * Your own row carries the way to undo it. Changing your mind, or standing
 * aside so a sibling can have something, is an ordinary thing to do — so it sits
 * quietly on your own entry rather than being an action on the item.
 */
export function Claimants({
  claims,
  onWithdraw,
  withdrawing,
}: {
  claims: Claimant[]
  /** Offered only when the signed-in person is one of the claimants. */
  onWithdraw?: () => void | Promise<void>
  withdrawing?: boolean
}) {
  const [asking, setAsking] = useState(false)

  if (claims.length === 0) return null

  return (
    <section className="claimants">
      <h2 className="eyebrow">Who's asked</h2>
      <ul className="claimants__list">
        {claims.map((claim) => (
          <li key={claim.claim_id} className="claimant">
            <div className="claimant__head">
              <span className="claimant__who">
                {claim.is_you ? 'You' : claim.claimant_name}
              </span>
              <span className="claimant__when">{when(claim.claimed_at)}</span>
            </div>
            {claim.comment ? (
              <p className="claimant__comment">“{claim.comment}”</p>
            ) : (
              // Saying nothing is explicitly allowed by the form's own wording,
              // so the absence is stated rather than left as a blank row.
              <p className="claimant__silent">Asked without saying why.</p>
            )}

            {claim.is_you && onWithdraw && (
              asking ? (
                <div className="claimant__ask">
                  <p className="claimant__question">
                    Take your name back off this one? You can always put it down
                    again later.
                  </p>
                  <div className="claimant__actions">
                    <button
                      className="button button--sage"
                      type="button"
                      disabled={withdrawing}
                      onClick={() => void onWithdraw()}
                    >
                      {withdrawing ? 'Taking it back…' : 'Yes, take it back'}
                    </button>
                    <button
                      className="button button--quiet"
                      type="button"
                      disabled={withdrawing}
                      onClick={() => setAsking(false)}
                    >
                      Keep it
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  className="claimant__withdraw"
                  type="button"
                  onClick={() => setAsking(true)}
                >
                  Take back your name
                </button>
              )
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
