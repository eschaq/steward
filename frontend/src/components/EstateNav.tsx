import { Link, NavLink } from 'react-router-dom'

import { StewardMark } from './StewardMark'

/** Mark, then the places there are to be.
 *
 * Sits in the dark hero on every signed-in screen, so the mark stays the way
 * home and the current section is always named rather than inferred from the
 * page title.
 */
export function EstateNav({
  active,
}: {
  active: 'inventory' | 'messages' | 'review'
}) {
  return (
    <nav className="estate-nav" aria-label="Estate">
      <Link to="/" className="estate-nav__mark" aria-label="Steward, back to the inventory">
        <StewardMark size={24} color="var(--on-ink)" />
      </Link>
      <NavLink
        to="/"
        className="estate-nav__link"
        aria-current={active === 'inventory' ? 'page' : undefined}
      >
        Inventory
      </NavLink>
      <NavLink
        to="/messages"
        className="estate-nav__link"
        aria-current={active === 'messages' ? 'page' : undefined}
      >
        Messages
      </NavLink>
      {/* Shown to everyone; the screen itself explains that working through the
          estate this way is the executor's job. Hiding it would leave a
          beneficiary wondering what they were missing. */}
      <NavLink
        to="/review"
        className="estate-nav__link"
        aria-current={active === 'review' ? 'page' : undefined}
      >
        Review
      </NavLink>
    </nav>
  )
}
