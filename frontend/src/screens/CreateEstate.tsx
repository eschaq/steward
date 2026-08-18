import { useState, type FormEvent } from 'react'

import { ApiError, createEstate } from '../api'
import { useAuth } from '../auth'
import { StewardMark } from '../components/StewardMark'
import type { EstateSummary } from '../api'

/** Where someone lands when they have no estate yet — and where they come back
 * to when they need a second one.
 *
 * One field. Not a setup wizard — a person arrives here shortly after a death,
 * and asking them to configure anything would be the wrong first thing to do.
 * Everything else the estate needs, Steward works out as they go.
 *
 * On Ink, like sign-in and the welcome: DESIGN.md keeps the dark surface for
 * arrival moments, and this is one.
 *
 * The same form serves both cases, with only the framing above it different.
 * "Nothing here yet" is true exactly once; saying it to someone who already has
 * an estate open would be a small lie, and the way out has to exist for them —
 * arriving with nothing, there is nowhere to go back to.
 */
export function CreateEstate({
  onCreated,
  another = false,
  onCancel,
}: {
  onCreated: (estate: EstateSummary) => void
  another?: boolean
  onCancel?: () => void
}) {
  const { user, leave } = useAuth()
  const [name, setName] = useState('')
  const [working, setWorking] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    setProblem(null)
    setWorking(true)
    try {
      onCreated(await createEstate(name.trim()))
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't set that up: ${error}`,
      )
      setWorking(false)
    }
  }

  return (
    <main className="welcome">
      <div className="welcome__panel">
        <header className="welcome__top">
          <StewardMark size={30} color="var(--on-ink)" />
          <button className="welcome__skip" type="button" onClick={() => void leave()}>
            Sign out
          </button>
        </header>

        <div className="welcome__body">
          <span className="eyebrow eyebrow--on-ink">
            {another ? 'Another estate' : 'Nothing here yet'}
          </span>
          <h1 className="welcome__title">What should we call it?</h1>
          <p className="welcome__text">
            A name for the estate you're looking after — most people use the
            house, or whose it was. You can change it later.
            {another && ' The one you have open stays exactly as it is.'}
          </p>

          <form className="create-estate" onSubmit={onSubmit}>
            <label className="create-estate__label" htmlFor="estate-name">
              The estate
            </label>
            <input
              id="estate-name"
              className="create-estate__input"
              type="text"
              placeholder="My mother's house"
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={working}
              autoFocus
              required
            />

            {problem && (
              <p className="notice notice--on-ink" role="alert">
                {problem}
              </p>
            )}

            <button
              className="button button--cream"
              type="submit"
              disabled={working || !name.trim()}
            >
              {working ? 'Setting it up…' : 'Start here'}
            </button>

            {onCancel && (
              <button
                className="welcome__skip create-estate__back"
                type="button"
                onClick={onCancel}
                disabled={working}
              >
                Never mind, go back
              </button>
            )}
          </form>
        </div>

        <footer className="welcome__foot">
          <p className="create-estate__who">Signed in as {user?.email}</p>
        </footer>
      </div>
    </main>
  )
}
