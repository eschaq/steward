import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AuthProvider, useAuth } from './auth'
import { Dashboard } from './screens/Dashboard'
import { ItemDetail } from './screens/ItemDetail'
import { MessageCenter } from './screens/MessageCenter'
import { ResolveItem } from './screens/ResolveItem'
import { Review } from './screens/Review'
import { SignIn } from './screens/SignIn'

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
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/items/:itemId" element={<ItemDetail />} />
      <Route path="/items/:itemId/resolve" element={<ResolveItem />} />
      <Route path="/messages" element={<MessageCenter />} />
      <Route path="/review" element={<Review />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
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
