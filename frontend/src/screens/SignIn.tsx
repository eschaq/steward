import { useState, type FormEvent } from 'react'

import { readableAuthError, useAuth } from '../auth'
import { StewardLockup } from '../components/StewardMark'

/** Sign-in: a full-bleed gable, the form sitting on it.
 *
 * The photograph is greyscale on disk and gets its colour from a clay-to-ink
 * duotone layer in CSS. That's what turns a picture of one particular building
 * into brand imagery rather than a stand-in for the family's own house — the
 * distinction docs/estate-agent-branding.md draws.
 *
 * Portrait and landscape crops of the same gable are swapped by media query in
 * index.css, so a phone gets the tall frame and a desktop the wide one.
 */
export function SignIn() {
  const { signIn } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [working, setWorking] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setProblem(null)
    setWorking(true)
    try {
      await signIn(email.trim(), password)
      // No navigation here: the auth listener swaps the screen once Firebase
      // reports the new user.
    } catch (error) {
      setProblem(readableAuthError(error))
      setWorking(false)
    }
  }

  return (
    <div className="signin">
      <div className="signin__photo" aria-hidden="true">
        <div className="signin__duotone" />
        <div className="signin__scrim" />
      </div>

      <main className="signin__body">
        <StewardLockup size={26} color="var(--on-ink)" />

        <div className="signin__welcome">
          <h1 className="signin__head">
            Welcome back,
            <br />
            take your time.
          </h1>
          <p className="signin__under">
            The house will be exactly where you left it.
          </p>
        </div>

        <form className="signin__form" onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {problem && (
            <p className="notice notice--on-ink" role="alert">
              {problem}
            </p>
          )}

          {/* Clay, not cream: with cream fields above it, a cream button reads as
              a third input rather than the thing you press. */}
          <button className="button button--primary" type="submit" disabled={working}>
            {working ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="signin__foot">
          Invited to an estate? Use the link in your invitation.
        </p>
      </main>
    </div>
  )
}
