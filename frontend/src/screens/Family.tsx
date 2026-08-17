import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, fetchMe, fetchMembers, inviteToEstate } from '../api'
import { useAuth } from '../auth'
import { EstateNav } from '../components/EstateNav'
import { estateId } from '../firebase'
import { ROLE_HELP, ROLE_LABEL, type Me, type Member } from '../types'

const ROLES = ['beneficiary', 'executor'] as const

function when(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

/** Who else is in this, and how to ask someone new.
 *
 * A screen of its own rather than a modal on the dashboard: the list is a
 * standing thing an executor comes back to — has she signed in yet? — not a
 * one-off action. It's also the fourth place the redesign always had, next to
 * Inventory, Messages and Review.
 *
 * Everyone can read the list; only the executor sees the form. Who else is here
 * is not privileged information inside a family.
 */
export function Family() {
  const { user, leave } = useAuth()
  const [me, setMe] = useState<Me | null>(null)
  const [members, setMembers] = useState<Member[] | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState<(typeof ROLES)[number]>('beneficiary')
  const [sending, setSending] = useState(false)
  const [invited, setInvited] = useState<{
    email: string
    emailed: boolean
    note: string | null
  } | null>(null)

  const load = useCallback(async () => {
    setProblem(null)
    try {
      const [standing, list] = await Promise.all([
        fetchMe(estateId()),
        fetchMembers(estateId()),
      ])
      setMe(standing)
      setMembers(list.members)
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't load the family: ${error}`,
      )
    } finally {
      setLoaded(true)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function invite(event: React.FormEvent) {
    event.preventDefault()
    const address = email.trim()
    if (!address) return
    setProblem(null)
    setInvited(null)
    setSending(true)
    try {
      const membership = await inviteToEstate(estateId(), {
        email: address,
        role,
        display_name: name.trim() || undefined,
      })
      setMembers((await fetchMembers(estateId())).members)
      setInvited({
        email: address,
        emailed: membership.invite_email_sent,
        note: membership.invite_email_note,
      })
      setEmail('')
      setName('')
    } catch (error) {
      setProblem(
        error instanceof ApiError ? error.message : `Couldn't send that invite: ${error}`,
      )
    } finally {
      setSending(false)
    }
  }

  const isExecutor = me?.role === 'executor'
  const waiting = (members ?? []).filter((m) => !m.accepted)
  const here = (members ?? []).filter((m) => m.accepted)

  return (
    <main className="page">
      <header className="hero hero--slim">
        <div className="hero__top">
          <EstateNav active="family" />
          <div className="hero__who">
            <span className="hero__email">{user?.email}</span>
            <button
              className="button button--ghost-ink"
              type="button"
              onClick={() => void leave()}
            >
              Sign out
            </button>
          </div>
        </div>
        <div>
          <div className="eyebrow eyebrow--on-ink">{me?.estate_name ?? estateId()}</div>
          <h1 className="display hero__title">Family</h1>
        </div>
      </header>

      {problem && (
        <p className="notice notice--problem" role="alert">
          <span>{problem}</span>
          <button className="button button--sage" type="button" onClick={() => void load()}>
            Try again
          </button>
        </p>
      )}

      {!loaded && <p className="notice">Looking up who's here…</p>}

      {loaded && isExecutor && (
        <section className="invite">
          <h2 className="eyebrow">Ask someone in</h2>
          <p className="invite__intro">
            They'll be able to look through everything and say what matters to
            them. You can change your mind later — nothing here is final.
          </p>

          <form className="invite__form" onSubmit={(event) => void invite(event)}>
            <div className="field">
              <label htmlFor="invite-email">Their email address</label>
              <input
                id="invite-email"
                type="email"
                autoComplete="off"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="ruth@example.com"
                required
              />
            </div>

            <div className="field">
              <label htmlFor="invite-name">What to call them</label>
              <input
                id="invite-name"
                type="text"
                autoComplete="off"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Ruth"
              />
            </div>

            <fieldset className="invite__roles">
              <legend>What they can do</legend>
              {ROLES.map((each) => (
                <label
                  key={each}
                  className={`invite__role${role === each ? ' invite__role--on' : ''}`}
                >
                  <input
                    type="radio"
                    name="role"
                    value={each}
                    checked={role === each}
                    onChange={() => setRole(each)}
                  />
                  <span className="invite__role-name">{ROLE_LABEL[each]}</span>
                  <span className="invite__role-help">{ROLE_HELP[each]}</span>
                </label>
              ))}
            </fieldset>

            <button
              className="button button--primary"
              type="submit"
              disabled={sending || !email.trim()}
            >
              {sending ? 'Asking…' : 'Send the invite'}
            </button>
          </form>

          {/* The server says what actually happened. A send that failed is
              reported as a send that failed — never smoothed over, because the
              executor is the only fallback and needs to know they are it. */}
          {invited && (
            <p
              className={`invite__done${invited.emailed ? '' : ' invite__done--quiet'}`}
              role="status"
            >
              {invited.emailed ? (
                <>
                  <strong>{invited.email}</strong> has been asked in, and an email
                  is on its way to them with a link to set a password. Once they
                  have, they'll show up under <em>Here</em>.
                </>
              ) : (
                <>
                  <strong>{invited.email}</strong> is on the list — that part is
                  recorded and safe. {invited.note} They can also get in from the
                  sign-in page with <em>Forgot your password?</em> and this
                  address.
                </>
              )}
            </p>
          )}
        </section>
      )}

      {loaded && members !== null && (
        <>
          {waiting.length > 0 && (
            <section className="family__group">
              <h2 className="family__heading">
                <span className="tag tag--unclaimed">Waiting to come in</span>
                <span className="review__count">
                  {waiting.length} {waiting.length === 1 ? 'person' : 'people'}
                </span>
              </h2>
              <ul className="family__list">
                {waiting.map((member) => (
                  <li className="family__row" key={member.user_id}>
                    <span className="family__who">
                      <span className="family__name">{member.display_name}</span>
                      <span className="family__email">{member.email}</span>
                    </span>
                    <span className="tag tag--routed">{ROLE_LABEL[member.role]}</span>
                    <span className="family__since">
                      Asked {when(member.invited_at)} — hasn't signed in yet
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="family__group">
            <h2 className="family__heading">
              <span className="tag tag--resolved">Here</span>
              <span className="review__count">
                {here.length} {here.length === 1 ? 'person' : 'people'}
              </span>
            </h2>
            {here.length === 0 ? (
              <p className="empty">Nobody has come in yet.</p>
            ) : (
              <ul className="family__list">
                {here.map((member) => (
                  <li className="family__row" key={member.user_id}>
                    <span className="family__who">
                      <span className="family__name">
                        {member.display_name}
                        {member.is_you && <span className="family__you">you</span>}
                      </span>
                      <span className="family__email">{member.email}</span>
                    </span>
                    <span className="tag tag--routed">{ROLE_LABEL[member.role]}</span>
                    <span className="family__since">
                      {member.accepted_at ? `Came in ${when(member.accepted_at)}` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      {loaded && !isExecutor && members !== null && (
        <div className="notice" style={{ marginTop: 18 }}>
          Asking someone new in is the executor's to do. Everything else here is
          the same for everyone — <Link to="/">the inventory</Link> is where the
          things are.
        </div>
      )}
    </main>
  )
}
