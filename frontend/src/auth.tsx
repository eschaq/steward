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
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signOut,
  type User,
} from 'firebase/auth'

import { useNavigate } from 'react-router-dom'

import { auth, clearEstateId } from './firebase'

interface AuthState {
  user: User | null
  /** False once Firebase has told us whether a session was restored. */
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  /** Create a real Firebase Auth account. Until this existed the only ways in
   * were an executor's invitation or a script, which meant nobody could try
   * the product. */
  signUp: (email: string, password: string) => Promise<void>
  /** Ask Firebase to email a link for setting a password.
   *
   * This is how an invited person gets in for the first time. An invite creates
   * their Auth account with no password at all, so there is nothing for them to
   * type until they've been through this — and they can't self-register the
   * address either, because it already exists. */
  sendResetEmail: (email: string) => Promise<void>
  leave: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

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
      signUp: async (email, password) => {
        await createUserWithEmailAndPassword(auth, email, password)
      },
      sendResetEmail: async (email) => {
        await sendPasswordResetEmail(auth, email)
      },
      leave: async () => {
        // The estate goes with the session: on a shared machine the next person
        // must not inherit the last one's.
        clearEstateId()
        await signOut(auth)
        // Clear the destination as well as the session. Without this the URL
        // survives sign-out, so on a shared laptop the next person to sign in
        // lands wherever the last one was reading — and "sign out" should mean
        // the session ended, not paused.
        //
        // `replace` so the signed-in URL doesn't sit in history behind them.
        //
        // Arriving at a URL is different: a deep link followed while signed out
        // still lands where it pointed once you sign in, which is what makes an
        // item link worth sending to someone.
        navigate('/', { replace: true })
      },
    }),
    [user, loading, navigate],
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
    // Sign-up's own failures. Without these the default branch shows people a
    // raw Firebase string at the moment they are trying to start.
    case 'auth/email-already-in-use':
      return 'There\'s already an account with that email — sign in instead?'
    case 'auth/weak-password':
      return 'That password is a bit short — six characters or more.'
    case 'auth/missing-password':
      return 'Put a password in as well.'
    case 'auth/operation-not-allowed':
      return "New accounts aren't switched on for this project yet."
    case 'auth/too-many-requests':
      return 'Too many attempts just now. Give it a minute and try again.'
    case 'auth/network-request-failed':
      return "Couldn't reach the sign-in service. Check your connection?"
    default:
      return `That didn't work: ${(error as Error)?.message ?? String(error)}`
  }
}
