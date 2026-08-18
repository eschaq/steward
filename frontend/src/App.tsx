import { useCallback, useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { acceptInvite, fetchMe, fetchMyEstates } from './api'
import { AuthProvider, useAuth } from './auth'
import { estateId, setEstateId } from './firebase'
import type { Me } from './types'
import { Dashboard } from './screens/Dashboard'
import { Family } from './screens/Family'
import { ItemDetail } from './screens/ItemDetail'
import { MessageCenter } from './screens/MessageCenter'
import { ResolveItem } from './screens/ResolveItem'
import { Review } from './screens/Review'
import { SignIn } from './screens/SignIn'
import { CreateEstate } from './screens/CreateEstate'
import { Welcome } from './screens/Welcome'

/** What happens between signing in and the inventory.
 *
 * Someone with an invite still waiting has it accepted for them here — there is
 * nothing to decide, they already followed the link — and if that acceptance is
 * what flipped a pending invite, they are new, and get shown around once.
 *
 * The "once" is the server's answer, not a stored flag: `first_accept` is true
 * only for the call that actually flipped `accepted_at`. EstateMembership's
 * fields are fixed by the data model doc, and "have they been welcomed" was
 * already answerable from whether the invite was still pending. Every later
 * sign-in accepts nothing, so it comes back false and lands on the dashboard.
 */
function Arrival({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  const [me, setMe] = useState<Me | null>(null)
  const [checked, setChecked] = useState(false)
  const [welcoming, setWelcoming] = useState(false)
  // null = still asking; 0 = nowhere to go yet.
  const [estateCount, setEstateCount] = useState<number | null>(null)

  const arrive = useCallback(async () => {
    try {
      // Order matters, and getting it wrong is what broke this once already:
      //
      //   1. ask where we belong AND who is waiting on an answer
      //   2. answer any invitations
      //   3. only then decide whether there is anywhere to go
      //
      // The bug: step 3 ran first and returned early. `/me/estates` counts
      // *accepted* memberships, so a freshly invited person has zero — they
      // looked exactly like a brand-new account and were shown "create your own
      // estate" while a real invitation to a real estate sat unanswered behind
      // it. The accept step further down was never reached.
      //
      // It could not have worked from there anyway: it called fetchMe with
      // `estateId()`, which for a new invitee is the *fallback* estate, not the
      // one that invited them. It only ever worked back when there was a single
      // estate whose id was a build-time constant.
      let mine = await fetchMyEstates()

      // Accept everything pending, not just the first. Two invitations mean two
      // families are waiting, and answering one of them is not an answer.
      if (mine.invitations.length > 0) {
        let firstTime = false
        for (const invitation of mine.invitations) {
          try {
            // `first_accept` is the server's own answer to "is this the call
            // that flipped it", so being welcomed once survives a refresh
            // without anything being stored client-side.
            const accepted = await acceptInvite(invitation.id)
            if (accepted.first_accept) firstTime = true
          } catch {
            // One invitation that won't accept must not strand the others, or
            // the estate this person actually uses. Their standing on it is
            // unchanged, so it will be offered again next time.
          }
        }
        if (firstTime) setWelcoming(true)
        // Re-ask, because what was pending a moment ago is now somewhere they
        // belong — and the choice below is made from that list.
        mine = await fetchMyEstates()
      }

      setEstateCount(mine.count)
      if (mine.count === 0) {
        setChecked(true)
        return
      }

      // Whichever estate was last chosen, if it is still one this account
      // belongs to — otherwise the oldest. This used to unconditionally take
      // the oldest, which is what made a switcher impossible: every reload
      // silently undid the choice. Membership is re-checked here rather than
      // trusted from localStorage, so an estate someone was removed from
      // cannot be pinned open by a stale browser.
      //
      // A person who just accepted their first invitation has no stored estate,
      // so this lands them on the one that invited them.
      const stored = estateId()
      const chosen = mine.estates.find((e) => e.id === stored) ?? mine.estates[0]
      setEstateId(chosen.id)

      setMe(await fetchMe(chosen.id))
    } catch {
      // A failure here is not worth a wall in front of the app: the screens
      // each ask for their own standing and say plainly what they find.
    } finally {
      setChecked(true)
    }
  }, [])

  useEffect(() => {
    void arrive()
  }, [arrive])

  // Held rather than flashed: showing the dashboard for a beat and then
  // replacing it with a welcome is worse than a moment of nothing.
  if (!checked) return null

  // A brand-new account, with nowhere to go until it makes somewhere.
  if (estateCount === 0) {
    return (
      <CreateEstate
        onCreated={(estate) => {
          setEstateId(estate.id)
          setEstateCount(1)
          void arrive()
        }}
      />
    )
  }

  if (welcoming && me) {
    return (
      <Welcome
        me={me}
        onDone={() => {
          setWelcoming(false)
          navigate('/', { replace: true })
        }}
      />
    )
  }
  return <>{children}</>
}

/** Starting a second estate, from inside the first.
 *
 * The same screen `<Arrival>` shows an account with nothing, reached
 * deliberately instead of by having nowhere else to be — so it says "another
 * estate" and offers a way back.
 *
 * Lands in the new estate on a full load, for the reason the switcher does:
 * every mounted screen is holding the previous estate's data.
 */
function NewEstate() {
  const navigate = useNavigate()
  return (
    <CreateEstate
      another
      onCancel={() => navigate(-1)}
      onCreated={(estate) => {
        setEstateId(estate.id)
        window.location.assign('/')
      }}
    />
  )
}

/** Signed out, there is one screen and it isn't addressable. Signed in, items
 * have real URLs — a contested piece is a thing a family will send each other a
 * link to. */
function Routed() {
  const { user, loading } = useAuth()

  // Firebase restores a session asynchronously. Rendering the sign-in screen
  // first would flash it at someone who is already signed in.
  if (loading) return null
  if (!user) return <SignIn />

  return (
    <Arrival>
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/items/:itemId" element={<ItemDetail />} />
      <Route path="/items/:itemId/resolve" element={<ResolveItem />} />
      <Route path="/messages" element={<MessageCenter />} />
      {/* Review is three addressable sections, not one long scroll. The bare
          path lands on the working table, which is what people come for. */}
      <Route path="/review" element={<Navigate to="/review/inventory" replace />} />
      <Route path="/review/:tab" element={<Review />} />
      <Route path="/family" element={<Family />} />
      <Route path="/estates/new" element={<NewEstate />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Arrival>
  )
}

/** Router outside the auth provider, so signing out can clear the URL.
 *
 * Nothing above <Routed> needs auth, and useNavigate only works inside a
 * router — so the provider goes in, not the other way round.
 */
export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routed />
      </AuthProvider>
    </BrowserRouter>
  )
}
