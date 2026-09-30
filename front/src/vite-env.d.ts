/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public API base URL; defaults to http://localhost:8000. */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
