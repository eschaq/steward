import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError, fetchMyEstates, type EstateSummary } from '../api'
import { estateId, setEstateId } from '../firebase'
import { ROLE_LABEL } from '../types'

/** Which estate you are looking at, and how to look at another one.
 *
 * **Why it lives on the estate name rather than on the Family screen.** Which
 * estate is current is not a setting — it is the context every screen is drawn
 * in, and the name in the hero is already the app's answer to "where am I". A
 * switcher anywhere else would leave that name looking like a label when it is
 * really the thing you are standing in. It appears on all four signed-in
 * screens for the same reason.
 *
 * Until now an account with two estates silently got the oldest one and a
 * console warning. That was honest about the limitation and useless to the
 * person hitting it.
 *
 * **Switching reloads the app rather than re-rendering it.** Every screen holds
 * items, members and messages it fetched for the estate that was current when
 * it mounted. Soft-navigating would leave one estate's belongings under
 * another's name for as long as it took each screen to notice — briefly, but
 * visibly, and in a product about whose things are whose that is the worst
 * possible glitch. A reload is a beat slower and cannot be wrong.
 *
 * **The panel is `position: fixed`.** `.hero` is `overflow: hidden` so it can
 * clip the gable photograph to its 22px radius; an absolutely-positioned menu
 * inside it would be cut off at the hero's edge. Fixed escapes that clip — the
 * hero sets no transform or filter, so it doesn't become a containing block.
 */
export function EstateSwitcher({ name }: { name: string }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [estates, setEstates] = useState<EstateSummary[] | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const wrap = useRef<HTMLDivElement>(null)

  // Asked for on first open, not on mount: this sits on every signed-in screen,
  // and most visits never touch it.
  const load = useCallback(async () => {
    try {
      setEstates((await fetchMyEstates()).estates)
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't list your estates: ${error}`,
      )
    }
  }, [])

  useEffect(() => {
    if (open && estates === null && problem === null) void load()
  }, [open, estates, problem, load])

  // Escape closes, and a click anywhere else closes. Both, because a menu you
  // can only dismiss by hitting the same small button again is a trap.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
    }
  }, [open])

  const current = estateId()

  function switchTo(estate: EstateSummary) {
    if (estate.id === current) {
      setOpen(false)
      return
    }
    setEstateId(estate.id)
    // Straight to the inventory, and a full load — see the note above.
    window.location.assign('/')
  }

  return (
    <div className="switcher" ref={wrap}>
      <button
        className="switcher__current eyebrow eyebrow--on-ink"
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        {name}
        <span className="switcher__caret" aria-hidden="true" />
      </button>

      {open && (
        <div className="switcher__panel" role="menu">
          <p className="switcher__head">Estates you're part of</p>

          {problem && <p className="switcher__problem">{problem}</p>}

          {estates === null && !problem && (
            <p className="switcher__quiet">Looking…</p>
          )}

          {estates?.map((estate) => (
            <button
              className="switcher__estate"
              type="button"
              role="menuitem"
              key={estate.id}
              aria-current={estate.id === current ? 'true' : undefined}
              onClick={() => switchTo(estate)}
            >
              <span className="switcher__name">{estate.name}</span>
              <span className="switcher__role">
                {ROLE_LABEL[estate.role] ?? estate.role}
                {estate.id === current && " · you're here"}
              </span>
            </button>
          ))}

          <button
            className="switcher__new"
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              navigate('/estates/new')
            }}
          >
            Start another estate
          </button>
        </div>
      )}
    </div>
  )
}
