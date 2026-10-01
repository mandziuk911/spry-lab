import { useEffect, useState } from "react"
import type { Meeting } from "@/types"

export const FINISHED_VISIBILITY_MS = 60 * 60 * 1000
export type MeetingStatus = "scheduled" | "in-progress" | "finished"
export const statusLabels: Record<MeetingStatus, string> = {
  scheduled: "Scheduled",
  "in-progress": "In progress",
  finished: "Finished",
}

export function meetingStatus(meeting: Meeting, now: number): MeetingStatus {
  if (now < Date.parse(meeting.starts_at)) return "scheduled"
  if (now < Date.parse(meeting.ends_at)) return "in-progress"
  return "finished"
}

export function isMeetingVisible(meeting: Meeting, now: number): boolean {
  return now < Date.parse(meeting.ends_at) + FINISHED_VISIBILITY_MS
}

export function useLiveNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const update = () => setNow(Date.now())
    const interval = window.setInterval(update, 1000)
    window.addEventListener("focus", update)
    document.addEventListener("visibilitychange", update)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener("focus", update)
      document.removeEventListener("visibilitychange", update)
    }
  }, [])
  return now
}
