import type { Balance } from '../types'

/** Whole pounds-and-pence would imply a precision nobody has. */
function roughly(value: number): string {
  if (value < 100) return `about $${Math.round(value / 5) * 5}`
  return `about $${Math.round(value / 25) * 25}`
}

/** How the belongings that went to people have landed so far.
 *
 * This is the most dangerous panel in the product to get wrong. A per-person
 * value tally is one design decision away from a scoreboard, and a scoreboard
 * in a house where somebody has just died would make a hard conversation
 * worse. Everything here is shaped against that:
 *
 *   - **Ordered by name, never by amount.** Sorting by value makes a league
 *     table whatever the words around it say. That ordering is done on the
 *     server so a careless client change cannot undo it.
 *   - **No bars, no charts, no percentages.** A bar chart is a race. Counts and
 *     a rough figure in a sentence are not.
 *   - **Items first, value second.** What someone kept is the real fact; what
 *     it is notionally worth is a guess laid over it.
 *   - **Rounded hard.** "About $105" invites arithmetic; "about $105" rounded
 *     to the nearest 25 above 100 says plainly that this is a ballpark.
 *   - **No verdict.** Steward does not say whether this is fair. It says what
 *     is there, notes plainly when the gap is wide, and leaves the judgement
 *     with the family, whose business it is.
 *
 * It also says what it is *not* counting — sold and donated things, and items
 * settled without naming anyone — because a total that silently omits half an
 * estate is worse than no total.
 */
export function HowItsLanded({ balance }: { balance: Balance | null }) {
  if (!balance) return null

  const { people, assigned_items, valued_items, not_to_a_person, unattributed } = balance

  if (people.length === 0) {
    return (
      <section className="landed">
        <h2 className="eyebrow">How things have landed</h2>
        <p className="landed__empty">
          Nothing has been settled to anyone in particular yet. Once things start
          going to people, this is where you can see roughly how it's spread —
          gently, and with no scores kept.
        </p>
      </section>
    )
  }

  const totals = people
    .map((p) => p.rough_total)
    .filter((t): t is number => t !== null)
  // Only worth remarking on when there is something to remark on, and only as
  // an observation. Never a judgement, never a recommendation to "rebalance".
  const wideGap =
    totals.length > 1 && Math.max(...totals) >= Math.min(...totals) * 3

  return (
    <section className="landed">
      <h2 className="eyebrow">How things have landed</h2>
      <p className="landed__intro">
        Where things have gone so far, and roughly what they'd fetch second-hand.
        Nothing here is final, and the figures are guesses rather than
        valuations — most of what makes any of this matter isn't a number at all.
      </p>

      <ul className="landed__people">
        {people.map((p) => (
          <li className="landed__person" key={p.user_id}>
            <span className="landed__name">{p.name}</span>
            <span className="landed__items">
              {p.items} {p.items === 1 ? 'thing' : 'things'}
            </span>
            <span className="landed__value">
              {p.rough_total === null
                ? 'no estimate yet'
                : roughly(p.rough_total)}
              {p.unvalued > 0 && (
                <span className="landed__caveat">
                  {' '}
                  ({p.unvalued} without an estimate)
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>

      {wideGap && (
        <p className="landed__note">
          That's a wide spread. It may be exactly right — one person may have
          taken the things nobody else wanted, or the piece that mattered most.
          It's only here so nobody finds out later.
        </p>
      )}

      <p className="landed__scope">
        Counting {valued_items} of {assigned_items}{' '}
        {assigned_items === 1 ? 'thing' : 'things'} that went to someone.
        {not_to_a_person > 0 && (
          <>
            {' '}
            Another {not_to_a_person} {not_to_a_person === 1 ? 'was' : 'were'}{' '}
            sold, given away or let go — those didn't come to anybody, so they're
            not in the tally.
          </>
        )}
        {unattributed > 0 && (
          <>
            {' '}
            {unattributed} {unattributed === 1 ? 'was' : 'were'} settled without
            naming anyone.
          </>
        )}
      </p>
    </section>
  )
}
