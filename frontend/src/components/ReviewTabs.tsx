import { NavLink } from 'react-router-dom'

/** The three things the Review screen is for, as three addressable places.
 *
 * They were stacked on one page: two reflective panels above the table the
 * executor actually works in. That put the slow, considered reading of an
 * estate — how it has landed, what Steward has learned — in front of the quick
 * task of clearing decisions, every single visit. The panels are worth having;
 * they are not worth scrolling past forty times an afternoon.
 *
 * Each is a real URL rather than a scroll position, so "look at how it's
 * landed" is a link somebody can send.
 *
 * Marked the same way as the app bar — a rule beneath the current one, not a
 * filled chip — because chips in this system are archival tags on objects and
 * pills are actions, and this is neither. It is where you are.
 */
export const REVIEW_TABS = [
  // Default and first: the working table is the reason most people open this
  // screen, so it is what the bare /review resolves to.
  { key: 'inventory', label: 'Inventory' },
  { key: 'landed', label: 'Where things have landed' },
  { key: 'learned', label: 'What Steward has learned' },
] as const

export type ReviewTab = (typeof REVIEW_TABS)[number]['key']

export const DEFAULT_TAB: ReviewTab = 'inventory'

export function isReviewTab(value: string | undefined): value is ReviewTab {
  return REVIEW_TABS.some((t) => t.key === value)
}

/** Shown to every member, executor or not.
 *
 * The two reflective tabs are readable by anyone in the family — who has ended
 * up with what is their own business — and the Inventory tab says in plain
 * words that working through the estate is the executor's job rather than
 * hiding itself. Hiding a tab leaves someone wondering what they can't see;
 * that is the same call the app bar already made about Review itself.
 */
export function ReviewTabs({ active }: { active: ReviewTab }) {
  return (
    <nav className="subtabs" aria-label="Review sections">
      {REVIEW_TABS.map((tab) => (
        <NavLink
          key={tab.key}
          to={`/review/${tab.key}`}
          className="subtab"
          aria-current={active === tab.key ? 'page' : undefined}
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
