import type { CreateMeeting, Meeting } from "@/types"

function meetingsUrl() {
  return `${(import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "")}/api/meetings`
}

export async function listMeetings(signal?: AbortSignal): Promise<Meeting[]> {
  const response = await fetch(meetingsUrl(), { signal })
  if (response.status !== 200) throw new Error("Could not load meetings. Please try again.")
  return response.json() as Promise<Meeting[]>
}

export type DeleteMeetingResult = "deleted" | "already-removed"

export async function deleteMeeting(id: Meeting["id"]): Promise<DeleteMeetingResult> {
  try {
    const response = await fetch(`${meetingsUrl()}/${encodeURIComponent(id)}`, { method: "DELETE" })
    if (response.status === 204) return "deleted"
    if (response.status === 404) return "already-removed"
    throw new Error("Deletion failed")
  } catch {
    throw new Error(
      "Could not delete the meeting. It has been kept on your desk. Check your connection and try again.",
    )
  }
}

export async function createMeeting(meeting: CreateMeeting): Promise<void> {
  const response = await fetch(meetingsUrl(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(meeting),
  })
  if (response.status !== 201) {
    throw new Error(
      response.status === 422
        ? "The server rejected these details. Check the fields and try again."
        : "Could not create the meeting. Your details have been kept. Please try again.",
    )
  }
}
