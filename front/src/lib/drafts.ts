export interface Draft {
  title: string
  start: string
  end: string
  count: string
}
const prefix = "spry.draft."
export const draftKey = (issuer: string, sub: string) => `${prefix}${JSON.stringify([issuer, sub])}`
export function readDraft(key: string): Draft | null {
  try {
    const draft: unknown = JSON.parse(sessionStorage.getItem(key) || "null")
    if (!draft || typeof draft !== "object") return null
    const record = draft as Record<string, unknown>
    const fields = ["title", "start", "end", "count"] as const
    if (
      Object.keys(record).length !== 4 ||
      !fields.every((field) => typeof record[field] === "string" && record[field].length <= 1000)
    )
      return null
    return record as unknown as Draft
  } catch {
    return null
  }
}
export function saveDraft(key: string, draft: Draft) {
  try {
    sessionStorage.setItem(key, JSON.stringify(draft))
  } catch {
    /* Storage unavailable: do not block sign-in. */
  }
}
export function clearDraft(key: string) {
  sessionStorage.removeItem(key)
}
export function clearDrafts() {
  for (const key of Object.keys(sessionStorage))
    if (key.startsWith(prefix)) sessionStorage.removeItem(key)
}
