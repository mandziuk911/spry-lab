import { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import type { Meeting } from "@/types"

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" })

function Appointment({
  meeting,
  onDelete,
}: {
  meeting: Meeting
  onDelete: (meeting: Meeting) => Promise<void>
}) {
  const [confirming, setConfirming] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")
  const locked = useRef(false)
  const trigger = useRef<HTMLButtonElement>(null)
  const start = new Date(meeting.starts_at)

  async function confirm() {
    if (locked.current) return
    locked.current = true
    setPending(true)
    setError("")
    try {
      await onDelete(meeting)
      document.getElementById("list-heading")?.focus()
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Could not delete the meeting. Please try again.",
      )
    } finally {
      locked.current = false
      setPending(false)
    }
  }

  return (
    <li className="appointment">
      <div className="appointment-title">
        <span className="date-badge" aria-hidden="true">
          <span>{start.toLocaleDateString(undefined, { month: "short" })}</span>
          <strong>{start.getDate()}</strong>
        </span>
        <div>
          <p className="appointment-kind">Scheduled conversation</p>
          <h3>{meeting.title}</h3>
        </div>
      </div>
      <dl className="appointment-details">
        <div>
          <dt>Start</dt>
          <dd>
            <time dateTime={meeting.starts_at}>{dateFormat.format(start)}</time>
          </dd>
        </div>
        <div>
          <dt>End</dt>
          <dd>
            <time dateTime={meeting.ends_at}>{dateFormat.format(new Date(meeting.ends_at))}</time>
          </dd>
        </div>
        <div>
          <dt>Attendees</dt>
          <dd>{meeting.attendee_count}</dd>
        </div>
      </dl>
      <div className="appointment-tools">
        <span>Shared appointment</span>
        {!confirming && (
          <Button
            ref={trigger}
            variant="outline"
            onClick={() => setConfirming(true)}
            aria-label={`Delete ${meeting.title}`}
          >
            Delete
          </Button>
        )}
      </div>
      {confirming && (
        <div
          className="delete-confirm"
          role="group"
          aria-label={`Confirm deletion of ${meeting.title}`}
        >
          <p>
            Delete <strong>“{meeting.title}”</strong>? This action is permanent and cannot be
            undone.
          </p>
          <div className="confirm-actions">
            <Button
              variant="outline"
              autoFocus
              disabled={pending}
              onClick={() => {
                setConfirming(false)
                setError("")
                requestAnimationFrame(() => trigger.current?.focus())
              }}
            >
              Cancel deletion
            </Button>
            <Button className="delete-button" disabled={pending} onClick={() => void confirm()}>
              {pending ? "Deleting…" : "Permanently delete meeting"}
            </Button>
          </div>
          {error && (
            <p role="alert" className="delete-error">
              {error}
            </p>
          )}
        </div>
      )}
    </li>
  )
}

export function MeetingList({
  meetings,
  onDelete,
}: {
  meetings: Meeting[]
  onDelete: (meeting: Meeting) => Promise<void>
}) {
  if (!meetings.length)
    return (
      <div className="empty-desk">
        <span aria-hidden="true" className="empty-icon">
          ✉
        </span>
        <h3>No meetings yet</h3>
        <p>Create your first meeting to get started.</p>
      </div>
    )
  return (
    <ul className="appointment-list" aria-label="Meetings">
      {meetings.map((meeting) => (
        <Appointment key={meeting.id} meeting={meeting} onDelete={onDelete} />
      ))}
    </ul>
  )
}
