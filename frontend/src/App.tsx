import { AuthProvider, useAuth } from './auth'
import { Dashboard } from './screens/Dashboard'
import { SignIn } from './screens/SignIn'

/** Two screens, chosen by whether anyone is signed in.
 *
 * No router yet — there is nowhere else to go until the item detail view and
 * the Message Center exist.
 */
function Routed() {
  const { user, loading } = useAuth()

  // Firebase restores a session asynchronously. Rendering the sign-in screen
  // first would flash it at someone who is already signed in.
  if (loading) return null

  return user ? <Dashboard /> : <SignIn />
}

export function App() {
  return (
    <AuthProvider>
      <Routed />
    </AuthProvider>
  )
}
