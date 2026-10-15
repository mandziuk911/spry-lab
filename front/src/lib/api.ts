import type { CreateMeeting, Meeting } from "@/types"
import { assertSession, type Session } from "@/lib/session"
import { clearDraft } from "@/lib/drafts"

export class UncertainCreationError extends Error {}

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
    throw new Error("Session ended")
  }
  return response
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
