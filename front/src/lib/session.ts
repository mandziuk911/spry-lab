import { createContext, useContext } from "react"
import type { User } from "oidc-client-ts"

export interface Session {
  key: string
  email: string
  active: boolean
  user: User
  expire: () => void
  logout: () => void
}
// Mutable capability owned by one mounted auth lifetime, not React state.
export class SessionLifetime implements Session {
  active = true
  constructor(
    public key: string,
    public email: string,
    public user: User,
    public expire: () => void,
    public logout: () => void,
  ) {}
  updateUser(user: User) {
    this.user = user
  }
  activate() {
    this.active = true
  }
  invalidate() {
    this.active = false
  }
}
export const SessionContext = createContext<Session | null>(null)
export function useSession() {
  const session = useContext(SessionContext)
  if (!session) throw new Error("Authenticated session required")
  return session
}
export function assertSession(session: Session) {
  if (!session.active || session.user.expired || !session.user.access_token) {
    if (session.active) session.expire()
    throw new Error("Session ended. Sign in again; the operation was not replayed.")
  }
}
