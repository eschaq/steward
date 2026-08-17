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
      // Which estates does this account actually belong to? Everything below
      // used to assume exactly one, known at build time.
      const mine = await fetchMyEstates()
      setEstateCount(mine.count)
      if (mine.count === 0) {
        setChecked(true)
        return
      }
      // KNOWN LIMITATION: more than one estate picks the oldest and says so.
      // There is no estate switcher yet, and guessing further would be worse
      // than being clear about it.
      if (mine.count > 1) {
        console.warn(
          `[steward] This account belongs to ${mine.count} estates. ` +
            `Showing "${mine.estates[0].name}" — there is no switcher yet.`,
        )
      }
      setEstateId(mine.estates[0].id)

      let standing = await fetchMe(estateId())
      if (standing.invite_pending) {
        const accepted = await acceptInvite(estateId())
        standing = await fetchMe(estateId())
        if (accepted.first_accept) setWelcoming(true)
      }
      setMe(standing)
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
      <Route path="/review" element={<Review />} />
      <Route path="/family" element={<Family />} />
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
