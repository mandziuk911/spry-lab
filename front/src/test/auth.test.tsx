import { StrictMode } from "react"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { User, UserManager, OidcClient } from "oidc-client-ts"
import { webcrypto } from "node:crypto"
import App from "@/App"
import { authConfig, callbackComplete, logoutUrl, providerSettings } from "@/lib/auth"
import { clearDrafts, draftKey, readDraft, saveDraft } from "@/lib/drafts"

const mock = vi.hoisted(() => ({
  auth: {} as Record<string, unknown>,
  expired: () => {},
  failed: () => {},
}))
vi.mock("react-oidc-context", async (original) => ({
  ...(await original<typeof import("react-oidc-context")>()),
  useAuth: () => mock.auth,
}))
const config = {
  issuer: "https://issuer.example/pool",
  clientId: "spa",
  domain: "https://login.example",
}
function user(sub = "one", access = "access-one") {
  return new User({
    access_token: access,
    id_token: "DO-NOT-SEND-ID",
    refresh_token: "refresh",
    token_type: "Bearer",
    expires_at: Math.floor(Date.now() / 1000) + 900,
    profile: {
      sub,
      email: "same@example.com",
      iss: config.issuer,
      aud: "spa",
      exp: 9999999999,
      iat: 1,
    },
  })
}
function signedIn(value = user()) {
  mock.auth.user = value
  mock.auth.isAuthenticated = true
}
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } })
const meeting = {
  id: "abc",
  title: "Private meeting",
  starts_at: new Date(Date.now() + 3600000).toISOString(),
  ends_at: new Date(Date.now() + 7200000).toISOString(),
  attendee_count: 1,
}
beforeEach(() => {
  sessionStorage.clear()
  window.history.replaceState({}, "", "/")
  vi.stubEnv("VITE_COGNITO_ISSUER", config.issuer)
  vi.stubEnv("VITE_COGNITO_CLIENT_ID", config.clientId)
  vi.stubEnv("VITE_COGNITO_DOMAIN", config.domain)
  mock.auth = {
    user: null,
    isAuthenticated: false,
    isLoading: false,
    activeNavigator: undefined,
    error: undefined,
    signinRedirect: vi.fn().mockResolvedValue(undefined),
    removeUser: vi.fn().mockResolvedValue(undefined),
    stopSilentRenew: vi.fn(),
    events: {
      addAccessTokenExpired: (fn: () => void) => {
        mock.expired = fn
        return vi.fn()
      },
      addSilentRenewError: (fn: () => void) => {
        mock.failed = fn
        return vi.fn()
      },
    },
  }
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async () => json([])),
  )
})

it("guests never mount the workspace or request meetings", () => {
  render(<App />)
  expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument()
  expect(screen.queryByLabelText("Title")).not.toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
})
it("signed-in StrictMode replay keeps a usable authenticated workspace", async () => {
  signedIn()
  render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
  await screen.findByText("No meetings yet")
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
})
it("missing or invalid configuration fails closed", () => {
  vi.stubEnv("VITE_COGNITO_CLIENT_ID", "")
  signedIn()
  render(<App />)
  expect(screen.getByText(/configuration is missing/)).toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
  expect(authConfig()).toBeNull()
})
it("login redirects once under StrictMode and guest sign-in uses the library", async () => {
  window.history.replaceState({}, "", "/login/")
  render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
  await waitFor(() => expect(mock.auth.signinRedirect).toHaveBeenCalledTimes(1))
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }))
  expect(mock.auth.signinRedirect).toHaveBeenCalledTimes(1)
  expect(fetch).not.toHaveBeenCalled()
})
it("failed login redirect is retryable but never loops automatically", async () => {
  window.history.replaceState({}, "", "/login/")
  mock.auth.signinRedirect = vi.fn().mockRejectedValue(new Error("offline"))
  render(<App />)
  await screen.findByText(/Sign-in could not be completed/)
  expect(mock.auth.signinRedirect).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }))
  await waitFor(() => expect(mock.auth.signinRedirect).toHaveBeenCalledTimes(2))
  expect(fetch).not.toHaveBeenCalled()
})
it("callback cleans code/state and returns only to the fixed root", () => {
  window.history.replaceState(
    {},
    "",
    "/auth/callback/?code=secret&state=value&returnTo=https://evil.example",
  )
  callbackComplete()
  expect(window.location.pathname).toBe("/")
  expect(window.location.search).toBe("")
  expect(providerSettings(config).onSigninCallback).toBe(callbackComplete)
})
it("invalid callback shows a recoverable error with no meeting requests", () => {
  window.history.replaceState({}, "", "/auth/callback/")
  mock.auth.error = new Error("state mismatch")
  render(<App />)
  expect(screen.getByText(/Sign-in could not be completed/)).toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
})
it("uses access tokens on GET/POST/DELETE, never ID tokens", async () => {
  signedIn()
  const request = vi
    .fn()
    .mockResolvedValueOnce(json([meeting]))
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(json({}, 201))
    .mockResolvedValueOnce(json([]))
  vi.stubGlobal("fetch", request)
  render(<App />)
  await screen.findByRole("heading", { name: meeting.title })
  fireEvent.click(screen.getByRole("button", { name: `Delete ${meeting.title}` }))
  fireEvent.click(screen.getByRole("button", { name: "Permanently delete meeting" }))
  await screen.findByText(/deleted permanently/)
  fillDraft()
  fireEvent.click(screen.getByRole("button", { name: "Create meeting" }))
  await screen.findByText(/Meeting created successfully/)
  for (const [, options] of request.mock.calls)
    expect(options.headers.Authorization).toBe("Bearer access-one")
  expect(JSON.stringify(request.mock.calls)).not.toContain("DO-NOT-SEND-ID")
  expect(readDraft(draftKey(config.issuer, "one"))).toBeNull()
})
function fillDraft() {
  for (const [label, value] of [
    ["Title", "My draft"],
    ["Start", "2027-01-01T09:00"],
    ["End", "2027-01-01T10:00"],
    ["Attendee count", "3"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
}
it.each(["expired", "failed"])(
  "terminal %s clears meeting data/confirmation and preserves only same-user draft",
  async (event) => {
    signedIn()
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json([meeting])))
    render(<App />)
    await screen.findByRole("heading", { name: meeting.title })
    fillDraft()
    fireEvent.click(screen.getByRole("button", { name: `Delete ${meeting.title}` }))
    act(() => mock[event === "expired" ? "expired" : "failed"]())
    expect(screen.queryByRole("heading", { name: meeting.title })).not.toBeInTheDocument()
    expect(screen.queryByRole("group")).not.toBeInTheDocument()
    expect(screen.getByText(/session ended/)).toBeInTheDocument()
    expect(readDraft(draftKey(config.issuer, "one"))).toEqual({
      title: "My draft",
      start: "2027-01-01T09:00",
      end: "2027-01-01T10:00",
      count: "3",
    })
    expect(mock.auth.signinRedirect).not.toHaveBeenCalled()
  },
)
it.each(["expired", "missing refresh token"])(
  "a session that is %s fails closed without meeting requests",
  async (failure) => {
    const value = user()
    if (failure === "expired") value.expires_at = Math.floor(Date.now() / 1000) - 1
    else value.refresh_token = undefined
    signedIn(value)
    render(<App />)
    await screen.findByText(/session ended/)
    expect(fetch).not.toHaveBeenCalled()
  },
)
it("reauthentication restores the exact same issuer/sub draft without replaying a submission", async () => {
  signedIn()
  const view = render(<App />)
  await screen.findByText("No meetings yet")
  fillDraft()
  act(() => mock.expired())
  mock.auth.user = null
  mock.auth.isAuthenticated = false
  view.rerender(<App />)
  signedIn(user())
  view.rerender(<App />)
  await screen.findByText("No meetings yet")
  expect(screen.getByLabelText("Title")).toHaveValue("My draft")
  expect(fetch).toHaveBeenCalledTimes(2)
  for (const [, options] of vi.mocked(fetch).mock.calls) expect(options?.method).toBeUndefined()
})
it("renewal keeps draft and workspace, and subsequent calls use the new token", async () => {
  signedIn()
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json([meeting])))
  const view = render(<App />)
  await screen.findByRole("heading", { name: meeting.title })
  fillDraft()
  signedIn(user("one", "renewed-access"))
  view.rerender(<App />)
  expect(screen.getByLabelText("Title")).toHaveValue("My draft")
  expect(fetch).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole("button", { name: `Delete ${meeting.title}` }))
  fireEvent.click(screen.getByRole("button", { name: "Permanently delete meeting" }))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  expect(vi.mocked(fetch).mock.calls[1][1]?.headers).toEqual({
    Authorization: "Bearer renewed-access",
  })
})
it.each(["GET", "POST", "DELETE"])(
  "401 on %s ends session with no retry or automatic redirect",
  async (method) => {
    signedIn()
    const request = vi
      .fn()
      .mockResolvedValueOnce(method === "GET" ? json({}, 401) : json([meeting]))
      .mockResolvedValue(json({}, 401))
    vi.stubGlobal("fetch", request)
    render(<App />)
    if (method !== "GET") {
      await screen.findByRole("heading", { name: meeting.title })
      if (method === "POST") {
        fillDraft()
        fireEvent.click(screen.getByRole("button", { name: "Create meeting" }))
      } else {
        fireEvent.click(screen.getByRole("button", { name: `Delete ${meeting.title}` }))
        fireEvent.click(screen.getByRole("button", { name: "Permanently delete meeting" }))
      }
    }
    await screen.findByText(/session ended/)
    expect(screen.queryByRole("heading", { name: meeting.title })).not.toBeInTheDocument()
    expect(request).toHaveBeenCalledTimes(method === "GET" ? 1 : 2)
    expect(mock.auth.signinRedirect).not.toHaveBeenCalled()
  },
)
it("drafts are isolated by issuer/sub, not shared email; malformed records are rejected", async () => {
  saveDraft(draftKey(config.issuer, "one"), {
    title: "Secret draft",
    start: "",
    end: "",
    count: "0",
  })
  signedIn(user("two"))
  const view = render(<App />)
  await screen.findByText("No meetings yet")
  expect(screen.getByLabelText("Title")).toHaveValue("")
  view.unmount()
  signedIn(user("one"))
  render(<App />)
  expect(screen.getByLabelText("Title")).toHaveValue("Secret draft")
  expect(readDraft(draftKey("https://different.example", "one"))).toBeNull()
  sessionStorage.setItem("bad", JSON.stringify({ title: "x", access_token: "bad" }))
  expect(readDraft("bad")).toBeNull()
})
it("logout clears local data/drafts and uses Cognito custom allowlisted logout URL", async () => {
  signedIn()
  render(<App />)
  await screen.findByText("No meetings yet")
  fillDraft()
  sessionStorage.setItem("spry.oidc.state.fixture", "test-state")
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }))
  expect(sessionStorage.getItem("spry.oidc.state.fixture")).toBeNull()
  expect(screen.queryByLabelText("Title")).not.toBeInTheDocument()
  expect(readDraft(draftKey(config.issuer, "one"))).toBeNull()
  expect(mock.auth.removeUser).toHaveBeenCalledTimes(1)
  const url = new URL(logoutUrl(config))
  expect(url.origin + url.pathname).toBe("https://login.example/logout")
  expect(url.searchParams.get("logout_uri")).toBe(`${window.location.origin}/`)
  expect(url.searchParams.get("client_id")).toBe("spa")
  clearDrafts()
})
it.each(["GET", "POST", "DELETE"])(
  "late %s from old identity cannot change the new session or its draft",
  async (method) => {
    signedIn()
    let resolve!: (response: Response) => void
    const pending = new Promise<Response>((done) => {
      resolve = done
    })
    const request = vi
      .fn()
      .mockResolvedValueOnce(method === "GET" ? pending : json([meeting]))
      .mockReturnValueOnce(method === "GET" ? json([]) : pending)
      .mockResolvedValue(json([]))
    vi.stubGlobal("fetch", request)
    const view = render(<App />)
    if (method !== "GET") {
      await screen.findByRole("heading", { name: meeting.title })
      if (method === "POST") {
        fillDraft()
        fireEvent.click(screen.getByRole("button", { name: "Create meeting" }))
      } else {
        fireEvent.click(screen.getByRole("button", { name: `Delete ${meeting.title}` }))
        fireEvent.click(screen.getByRole("button", { name: "Permanently delete meeting" }))
      }
    }
    signedIn(user("two", "access-two"))
    view.rerender(<App />)
    await screen.findByText("No meetings yet")
    fillDraft()
    await act(async () =>
      resolve(
        method === "DELETE"
          ? new Response(null, { status: 204 })
          : json(method === "GET" ? [meeting] : {}, method === "POST" ? 201 : 200),
      ),
    )
    expect(screen.queryByRole("heading", { name: meeting.title })).not.toBeInTheDocument()
    expect(screen.getByLabelText("Title")).toHaveValue("My draft")
    expect(screen.queryByText(/created successfully|deleted permanently/)).not.toBeInTheDocument()
  },
)
it("pinned library creates PKCE/state in sessionStorage and rejects missing/replayed callback state", async () => {
  vi.stubGlobal("crypto", webcrypto)
  const settings = {
    ...providerSettings(config),
    metadata: {
      issuer: config.issuer,
      authorization_endpoint: `${config.domain}/oauth2/authorize`,
      token_endpoint: `${config.domain}/oauth2/token`,
    },
  }
  const client = new OidcClient(settings)
  const request = await client.createSigninRequest({
    redirect_uri: `${window.location.origin}/auth/callback/`,
    response_type: "code",
    scope: "openid email profile",
  })
  const url = new URL(request.url)
  expect(url.searchParams.get("code_challenge_method")).toBe("S256")
  expect(url.searchParams.get("state")).toBeTruthy()
  expect(url.searchParams.get("code_challenge")).toBeTruthy()
  expect(sessionStorage.length).toBeGreaterThan(0)
  expect(localStorage.length).toBe(0)
  await expect(
    client.processSigninResponse(`${window.location.origin}/auth/callback/?code=x&state=unknown`),
  ).rejects.toThrow()
  await expect(
    client.processSigninResponse(`${window.location.origin}/auth/callback/?code=x`),
  ).rejects.toThrow()
  // State is consumed even when the token exchange fails: no replay.
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "invalid_grant" }, 400)))
  const callback = `${window.location.origin}/auth/callback/?code=x&state=${url.searchParams.get("state")}`
  await expect(client.processSigninResponse(callback)).rejects.toThrow()
  await expect(client.processSigninResponse(callback)).rejects.toThrow(/state/i)
})
it("pinned library renews with refresh_token without an iframe/cookie session", async () => {
  const manager = new UserManager({
    ...providerSettings(config),
    automaticSilentRenew: false,
    loadUserInfo: false,
    metadata: { issuer: config.issuer, token_endpoint: `${config.domain}/oauth2/token` },
  })
  await manager.storeUser(user())
  const request = vi.fn().mockResolvedValue(
    json({
      access_token: "new-access",
      token_type: "Bearer",
      expires_in: 900,
      refresh_token: "new-refresh",
    }),
  )
  vi.stubGlobal("fetch", request)
  const renewed = await manager.signinSilent()
  expect(renewed?.access_token).toBe("new-access")
  expect(String(request.mock.calls[0][1].body)).toContain("grant_type=refresh_token")
  expect(document.querySelector("iframe")).toBeNull()
  expect((await manager.getUser())?.access_token).toBe("new-access")
  await manager.removeUser()
  manager.events.unload()
})
