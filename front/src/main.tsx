import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { AuthProvider } from "react-oidc-context"
import { authConfig, providerSettings } from "@/lib/auth"
import App from "@/App"
import "@/index.css"

const config = authConfig()
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {config ? (
      <AuthProvider {...providerSettings(config)}>
        <App />
      </AuthProvider>
    ) : (
      <main className="desktop">
        <section className="desk-window">
          <h1>Authentication configuration required</h1>
          <p>
            Set VITE_COGNITO_ISSUER, VITE_COGNITO_CLIENT_ID and VITE_COGNITO_DOMAIN. The meeting
            desk is unavailable until configuration is complete.
          </p>
        </section>
      </main>
    )}
  </StrictMode>,
)
