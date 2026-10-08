import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { hasAuthParams, useAuth } from "react-oidc-context"
import { Button } from "@/components/ui/button"
import { authConfig, clearOidcStorage, logoutUrl } from "@/lib/auth"
import { clearDrafts, draftKey } from "@/lib/drafts"
import { SessionContext, SessionLifetime } from "@/lib/session"

export function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuth()
  const config = authConfig()
  const [ended, setEnded] = useState<SessionLifetime | null>(null)
  const [redirectFailed, setRedirectFailed] = useState(false)
  const redirected = useRef(false)
  const user = auth.user
  const key = config && user?.profile.sub ? draftKey(config.issuer, user.profile.sub) : ""
  const session = useMemo<SessionLifetime | null>(() => {
    if (!key || !user) return null
    const value: SessionLifetime = new SessionLifetime(
      key,
      String(user.profile.email || "Signed-in user"),
      user,
      () => {
        if (!value.active) return
        value.invalidate()
        setEnded(value)
        auth.stopSilentRenew()
        void auth.removeUser().catch(() => {})
      },
      () => {
        value.invalidate()
        clearDrafts()
        clearOidcStorage()
        setEnded(value)
        auth.stopSilentRenew()
        void auth
          .removeUser()
          .catch(() => {})
          .finally(() => {
            if (config) window.location.assign(logoutUrl(config))
          })
      },
    )
    return value
    // Renewal changes tokens, not the workspace/draft identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  useLayoutEffect(() => {
    if (session && user) session.updateUser(user)
  }, [session, user])
  useLayoutEffect(() => {
    if (!session) return
    session.activate()
    return () => session.invalidate()
  }, [session])

  useEffect(() => {
    if (!session) return
    const expire = () => session.expire()
    const cleanupExpired = auth.events.addAccessTokenExpired(expire)
    const cleanupRenew = auth.events.addSilentRenewError(expire)
    // A public code-flow session must have a refresh token. Fail closed rather
    // than letting the library fall back to cookie-dependent iframe renewal.
    if (!session.user.refresh_token || session.user.expired) session.expire()
    return () => {
      cleanupExpired()
      cleanupRenew()
    }
  }, [session, auth.events])

  useEffect(() => {
    if (
      window.location.pathname !== "/login/" ||
      !config ||
      auth.isLoading ||
      auth.isAuthenticated ||
      auth.activeNavigator ||
      auth.error ||
      ended ||
      redirectFailed ||
      hasAuthParams() ||
      redirected.current
    )
      return
    redirected.current = true
    void auth.signinRedirect().catch(() => {
      redirected.current = false
      setRedirectFailed(true)
    })
  }, [auth, config, ended, redirectFailed])

  if (!config)
    return (
      <Welcome message="Authentication configuration is missing or invalid. Set VITE_COGNITO_ISSUER, VITE_COGNITO_CLIENT_ID and VITE_COGNITO_DOMAIN." />
    )
  if (auth.isLoading || auth.activeNavigator) return <Welcome message="Connecting securely…" />
  if (
    session &&
    auth.isAuthenticated &&
    user &&
    !user.expired &&
    !!user.refresh_token &&
    ended !== session &&
    !auth.error
  ) {
    return (
      <SessionContext.Provider value={session}>
        <div key={key}>{children}</div>
      </SessionContext.Provider>
    )
  }
  const message = ended
    ? "Your session ended. Sign in again. Pending operations were not replayed; check the meeting list before recreating an uncertain submission."
    : redirectFailed || auth.error || window.location.pathname === "/auth/callback/"
      ? "Sign-in could not be completed. Start a new sign-in from here."
      : "A little more together. Sign in to open the shared meeting desk."
  return (
    <Welcome
      message={message}
      signIn={() => {
        window.history.replaceState({}, document.title, "/login/")
        if (redirected.current) return
        redirected.current = true
        void auth.signinRedirect().catch(() => {
          redirected.current = false
          setRedirectFailed(true)
        })
      }}
    />
  )
}

function Welcome({ message, signIn }: { message: string; signIn?: () => void }) {
  return (
    <div className="desktop">
      <main className="desk-window">
        <header className="window-titlebar">Spry Meeting Desk</header>
        <div className="desk-banner">
          <div>
            <p className="eyebrow">Welcome to your shared desk</p>
            <h1>Spry</h1>
            <p role="status">{message}</p>
            {signIn && <Button onClick={signIn}>Sign in</Button>}
          </div>
        </div>
      </main>
    </div>
  )
}
