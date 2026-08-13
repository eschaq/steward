import { useState, type FormEvent } from 'react'

import { readableAuthError, useAuth } from '../auth'

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
      <main className="signin__card">
        <div>
          <h1 className="signin__brand">Steward</h1>
          <p className="signin__tagline body-lg">Decide together. Steward it well.</p>
        </div>

        <form className="signin__form" onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
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
            <p className="notice notice--problem" role="alert">
              {problem}
            </p>
          )}

          <button className="button button--primary" type="submit" disabled={working}>
            {working ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="muted label-md" style={{ margin: 0 }}>
          Invited to an estate? Sign in with the address the invitation went to.
        </p>
      </main>
    </div>
  )
}
