import type { AgendaSuggestion, CreateMeeting, Meeting, SavedAgenda } from "@/types"
import { assertSession, type Session } from "@/lib/session"
import { clearDraft } from "@/lib/drafts"

export class UncertainCreationError extends Error {}

export async function loadAgenda(
  session: Session,
  id: string,
  signal?: AbortSignal,
): Promise<SavedAgenda | null> {
  const response = await authorizedFetch(
    session,
    `${meetingsUrl()}/${encodeURIComponent(id)}/agenda`,
    { signal },
  )
  const body = await response.json()
  assertSession(session)
  if (response.status === 404) {
    if (body.detail === "Agenda not found") return null
    throw new Error("Meeting not found. This meeting may have been deleted.")
  }
  if (response.status !== 200) throw agendaError(response.status)
  return body as SavedAgenda
}

export async function saveAgenda(session: Session, id: string, agenda: SavedAgenda): Promise<void> {
  const response = await authorizedFetch(
    session,
    `${meetingsUrl()}/${encodeURIComponent(id)}/agenda`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(agenda),
    },
  )
  if (response.status === 404)
    throw new Error("Meeting not found. This meeting may have been deleted.")
  if (response.status !== 200) throw agendaError(response.status)
  assertSession(session)
}

export async function parseAgenda(
  session: Session,
  text: string,
  signal: AbortSignal,
): Promise<AgendaSuggestion> {
  if (text.length > 10000) throw agendaError(413)
  const url = import.meta.env.VITE_PARSER_URL?.trim()
  if (!url)
    throw new Error(
      "The agenda reader is not configured. You can still fill in and save the agenda manually.",
    )
  assertSession(session)
  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`
  let response: Response
  try {
    response = await fetch(url, {
      method: "POST",
      credentials: "omit",
      signal,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.user.access_token}`,
      },
      body: JSON.stringify({ text, today, tz: Intl.DateTimeFormat().resolvedOptions().timeZone }),
    })
  } catch (error) {
    assertSession(session)
    if (signal.aborted) throw error
    throw new Error(
      "Could not reach the agenda reader. Check your connection or enter the agenda manually.",
      { cause: error },
    )
  }
  assertSession(session)
  // A cancelled response must not expire a newer operation or change its fields.
  signal.throwIfAborted()
  if (response.status === 401) {
    session.expire()
    throw agendaError(401)
  }
  if (response.status !== 200) throw agendaError(response.status)
  let result: unknown
  try {
    result = await response.json()
  } catch (cause) {
    assertSession(session)
    signal.throwIfAborted()
    throw new Error(agendaError(502).message, { cause })
  }
  assertSession(session)
  signal.throwIfAborted()
  if (!isAgendaSuggestion(result)) throw agendaError(502)
  return result
}

function isAgendaSuggestion(value: unknown): value is AgendaSuggestion {
  if (!value || typeof value !== "object") return false
  const result = value as Record<string, unknown>
  if (
    typeof result.model !== "string" ||
    typeof result.prompt_version !== "string" ||
    !result.agenda ||
    typeof result.agenda !== "object"
  )
    return false
  const agenda = result.agenda as Record<string, unknown>
  const nullableText = (v: unknown) => v === null || typeof v === "string"
  const nullableNumber = (v: unknown) => v === null || (typeof v === "number" && Number.isFinite(v))
  const rows = (v: unknown, valid: (row: Record<string, unknown>) => boolean) =>
    Array.isArray(v) &&
    v.every(
      (row: unknown) =>
        row !== null && typeof row === "object" && valid(row as Record<string, unknown>),
    )
  return (
    nullableText(agenda.title) &&
    nullableText(agenda.starts_at) &&
    nullableNumber(agenda.duration_minutes) &&
    typeof agenda.language === "string" &&
    rows(
      agenda.items,
      (row) =>
        typeof row.topic === "string" && nullableText(row.owner) && nullableNumber(row.minutes),
    ) &&
    rows(
      agenda.action_items,
      (row) => typeof row.task === "string" && nullableText(row.owner) && nullableText(row.due),
    )
  )
}

async function authorizedFetch(session: Session, url: string, options: RequestInit = {}) {
  assertSession(session)
  const response = await fetch(url, {
    ...options,
    headers: { ...options.headers, Authorization: `Bearer ${session.user.access_token}` },
  })
  // Preserve a received acknowledgement even if this identity has since expired.
  // Clear only this identity's draft; never mutate the replacement desk.
  if (options.method === "POST" && response.status === 201) clearDraft(session.key)
  // A response from a signed-out/previous identity never changes the current desk.
  assertSession(session)
  if (response.status === 401) {
    session.expire()
    throw new Error("Session ended. Sign in again; the operation was not replayed.")
  }
  return response
}

export function agendaError(status: number): Error {
  const messages: Record<number, string> = {
    401: "Your session ended. Sign in again; nothing was retried.",
    413: "This agenda is too long. Shorten it to 10,000 characters or fewer.",
    422: "The agenda could not be read. Check the text or fill in the fields manually.",
    429: "The agenda reader is busy or its limit was reached. Try again later or enter it manually.",
    502: "The agenda reader is temporarily unavailable. Try again later or enter it manually.",
  }
  return new Error(
    messages[status] || "The agenda request failed. Your fields have been kept. Please try again.",
  )
}

function meetingsUrl() {
  return `${(import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "")}/api/meetings`
}

export async function listMeetings(session: Session, signal?: AbortSignal): Promise<Meeting[]> {
  const response = await authorizedFetch(session, meetingsUrl(), { signal })
  if (response.status !== 200) throw new Error("Could not load meetings. Please try again.")
  const meetings = (await response.json()) as Meeting[]
  assertSession(session)
  return meetings
}

export type DeleteMeetingResult = "deleted" | "already-removed"

export async function deleteMeeting(
  session: Session,
  id: Meeting["id"],
): Promise<DeleteMeetingResult> {
  try {
    const response = await authorizedFetch(session, `${meetingsUrl()}/${encodeURIComponent(id)}`, {
      method: "DELETE",
    })
    if (response.status === 204) return "deleted"
    if (response.status === 404) return "already-removed"
    throw new Error("Deletion failed")
  } catch {
    throw new Error(
      "Could not delete the meeting. It has been kept on your desk. Check your connection and try again.",
    )
  }
}

export async function createMeeting(session: Session, meeting: CreateMeeting): Promise<void> {
  let response: Response
  try {
    response = await authorizedFetch(session, meetingsUrl(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(meeting),
    })
  } catch {
    throw new UncertainCreationError(
      "Creation was not acknowledged. The meeting may have been saved. Check or reload the meeting list before resubmitting. Your details have been kept; nothing was replayed.",
    )
  }
  if (response.status >= 500) {
    throw new UncertainCreationError(
      "Creation was not acknowledged. Check or reload the meeting list before resubmitting. Your details have been kept; nothing was replayed.",
    )
  }
  if (response.status !== 201) {
    throw new Error(
      response.status === 422
        ? "The server rejected these details. Check the fields and try again."
        : "Could not create the meeting. Your details have been kept. Please try again.",
    )
  }
}
