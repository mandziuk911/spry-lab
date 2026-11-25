import { WebStorageStateStore, type UserManagerSettings } from "oidc-client-ts"
import type { AuthProviderProps } from "react-oidc-context"

export interface AuthConfig {
  issuer: string
  clientId: string
  domain: string
}
export function authConfig(): AuthConfig | null {
  const issuer = import.meta.env.VITE_COGNITO_ISSUER?.trim()
  const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID?.trim()
  const domain = import.meta.env.VITE_COGNITO_DOMAIN?.trim()
  if (!issuer || !clientId || !domain) return null
  try {
    for (const value of [issuer, domain]) {
      const url = new URL(value)
      if (url.protocol !== "https:" || url.search || url.hash || url.username || url.password)
        return null
    }
    if (new URL(domain).pathname !== "/") return null
    return { issuer: issuer.replace(/\/$/, ""), clientId, domain: new URL(domain).origin }
  } catch {
    return null
  }
}
export function callbackComplete() {
  window.history.replaceState({}, document.title, "/")
}
export function providerSettings(config: AuthConfig): AuthProviderProps & UserManagerSettings {
  return {
    authority: config.issuer,
    client_id: config.clientId,
    redirect_uri: `${window.location.origin}/auth/callback/`,
    response_type: "code",
    scope: "openid email profile",
    // Cognito's documented endpoints are fixed by the trusted build-time config.
    // Avoid a discovery round-trip that can time out in Safari/Private Relay.
    metadata: {
      issuer: config.issuer,
      authorization_endpoint: `${config.domain}/oauth2/authorize`,
      token_endpoint: `${config.domain}/oauth2/token`,
      userinfo_endpoint: `${config.domain}/oauth2/userInfo`,
      jwks_uri: `${config.issuer}/.well-known/jwks.json`,
      revocation_endpoint: `${config.domain}/oauth2/revoke`,
    },
    automaticSilentRenew: true,
    maxSilentRenewTimeoutRetries: 0,
    requestTimeoutInSeconds: 30,
    // Cognito refresh tokens, never cookie-only hidden iframe renewal.
    userStore: new WebStorageStateStore({
      store: window.sessionStorage,
      prefix: "spry.oidc.user.",
    }),
    stateStore: new WebStorageStateStore({
      store: window.sessionStorage,
      prefix: "spry.oidc.state.",
    }),
    onSigninCallback: callbackComplete,
  }
}
export function clearOidcStorage() {
  for (const key of Object.keys(sessionStorage)) {
    if (key.startsWith("spry.oidc.")) sessionStorage.removeItem(key)
  }
}
export function logoutUrl(config: AuthConfig) {
  const url = new URL("/logout", config.domain)
  url.searchParams.set("client_id", config.clientId)
  url.searchParams.set("logout_uri", `${window.location.origin}/`)
  return url.href
}
