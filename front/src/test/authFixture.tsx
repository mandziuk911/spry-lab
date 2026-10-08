import { beforeEach, vi } from "vitest"
import { User } from "oidc-client-ts"
import { draftKey } from "@/lib/drafts"

const fixture = vi.hoisted(() => ({ session: null as unknown }))
vi.mock("@/AuthGate", () => ({
  AuthGate: ({ children }: { children: React.ReactNode }) => children,
}))
vi.mock("@/lib/session", async (original) => ({
  ...(await original<typeof import("@/lib/session")>()),
  useSession: () => fixture.session,
}))
beforeEach(() => {
  sessionStorage.clear()
  fixture.session = {
    key: draftKey("https://issuer.example", "fixture"),
    email: "fixture@example.com",
    active: true,
    user: new User({
      access_token: "fixture-access",
      id_token: "never-send-id",
      token_type: "Bearer",
      profile: {
        sub: "fixture",
        iss: "https://issuer.example",
        aud: "client",
        exp: 9999999999,
        iat: 1,
      },
      expires_at: 9999999999,
    }),
    expire: vi.fn(),
    logout: vi.fn(),
  }
})
