/** Who is signed in, and the ID token that proves it. */

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut,
  type User,
} from 'firebase/auth'

import { auth } from './firebase'

interface AuthState {
  user: User | null
  /** False once Firebase has told us whether a session was restored. */
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  leave: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => onAuthStateChanged(auth, (next) => {
    setUser(next)
    setLoading(false)
  }), [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      signIn: async (email, password) => {
        await signInWithEmailAndPassword(auth, email, password)
      },
      leave: () => signOut(auth),
    }),
    [user, loading],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}

/** Firebase Auth's messages are written for developers. These are written for
 * someone sitting at a kitchen table who mistyped their password. */
export function readableAuthError(error: unknown): string {
  const code = (error as { code?: string })?.code ?? ''
  switch (code) {
    case 'auth/invalid-email':
      return "That doesn't look like an email address."
    case 'auth/invalid-credential':
    case 'auth/wrong-password':
    case 'auth/user-not-found':
      return "That email and password don't match an account. Worth another try?"
    case 'auth/too-many-requests':
      return 'Too many attempts just now. Give it a minute and try again.'
    case 'auth/network-request-failed':
      return "Couldn't reach the sign-in service. Check your connection?"
    default:
      return `Sign-in didn't work: ${(error as Error)?.message ?? String(error)}`
  }
}
