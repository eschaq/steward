import { useEffect, useRef, useState, type FormEvent } from 'react'

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
  const { signIn, sendResetEmail } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [working, setWorking] = useState(false)
  const [sent, setSent] = useState<string | null>(null)
  const hero = useRef<HTMLVideoElement>(null)

  /* Autoplay, made to actually happen.
   *
   * React applies `muted` as a DOM *property*, and never writes the attribute.
   * Chrome decides whether a video may autoplay by reading the **attribute** as
   * the element is parsed — so `<video muted autoPlay>` written in JSX arrives
   * at the browser looking unmuted, and gets blocked. It loads, paints its
   * poster, and sits there. (Headless Chromium is more permissive, which is
   * exactly why this got past the first round of verification.)
   *
   * So: set the attribute ourselves, then ask it to play. If the browser still
   * refuses — a data saver, battery saver, a policy we can't see — the poster
   * and the background photograph are already the right picture, and one retry
   * on the first interaction costs nothing.
   */
  useEffect(() => {
    const video = hero.current
    if (!video) return

    video.muted = true
    video.defaultMuted = true
    video.setAttribute('muted', '')

    let cancelled = false
    const start = () => {
      if (cancelled) return
      const attempt = video.play()
      if (attempt) attempt.catch(() => undefined)
    }
    start()

    // Some browsers only relax the policy once the page has been touched.
    const onInteract = () => start()
    window.addEventListener('pointerdown', onInteract, { once: true })
    window.addEventListener('keydown', onInteract, { once: true })
    return () => {
      cancelled = true
      window.removeEventListener('pointerdown', onInteract)
      window.removeEventListener('keydown', onInteract)
    }
  }, [])

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

  /** First time in for anyone who was invited.
   *
   * An invite creates the Auth account with no password, so there is nothing to
   * type until Firebase has emailed them a link to set one — and the address
   * can't be self-registered either, because the invite already claimed it.
   * This is the door.
   */
  async function onReset() {
    const address = email.trim()
    setProblem(null)
    setSent(null)
    if (!address) {
      setProblem('Put your email address in first, and we\'ll send the link there.')
      return
    }
    setWorking(true)
    try {
      await sendResetEmail(address)
      setSent(address)
    } catch (error) {
      setProblem(readableAuthError(error))
    } finally {
      setWorking(false)
    }
  }

  return (
    <div className="signin">
      <div className="signin__photo" aria-hidden="true">
        {/* `?v=` is a cache-buster, and it earns its keep: this file was
            replaced in place once already and browsers hold on to media hard —
            a range-requested video survives an ordinary hard refresh. Bump the
            token whenever the clip is regenerated or re-cut.

            The poster and the div's background-image are both frames from
            *this* clip, not the older gable stills — otherwise a failed video
            would fall back to a different building. If the
            video never loads — decode failure, a browser that blocks autoplay,
            a stripped-down data saver — the photograph is already there and
            nothing about the layout changes. `poster` is that same still, so
            the first painted frame matches either way. */}
        <video
          ref={hero}
          className="signin__video"
          src="/brand/hero-drift-loop.mp4?v=3"
          poster="/brand/hero-drift-poster.jpg"
          autoPlay
          loop
          muted
          playsInline
          preload="auto"
          tabIndex={-1}
        />
        <div className="signin__duotone" />
        <div className="signin__scrim" />
      </div>

      <main className="signin__body">
        <StewardLockup size={26} color="var(--on-ink)" />

        <div className="signin__welcome">
          <h1 className="signin__head">
            Welcome back.
            <br />
            Take your time.
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

          {sent && (
            <p className="notice notice--on-ink" role="status">
              Sent to {sent}. Follow the link to set a password, then come back
              and sign in.
            </p>
          )}

          {/* Clay, not cream: with cream fields above it, a cream button reads as
              a third input rather than the thing you press. */}
          <button className="button button--primary" type="submit" disabled={working}>
            {working ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <button
          className="signin__reset"
          type="button"
          onClick={() => void onReset()}
          disabled={working}
        >
          Forgot your password?
        </button>

        <p className="signin__foot">
          Just been invited? Put your email above and use that link — it's how you
          set a password the first time.
        </p>
      </main>
    </div>
  )
}
