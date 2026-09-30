import { useCallback, useEffect, useRef, useState } from "react"
import { MeetingForm } from "@/components/MeetingForm"
import { MeetingList } from "@/components/MeetingList"
import { Button } from "@/components/ui/button"
import { deleteMeeting, listMeetings } from "@/lib/api"
import type { Meeting } from "@/types"

export default function App() {
  const [meetings, setMeetings] = useState<Meeting[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [saved, setSaved] = useState(false)
  const [notice, setNotice] = useState("")
  const request = useRef(0)
  const mutationGeneration = useRef(0)
  // Session-local deletion tombstones guard even refreshes started during a DELETE.
  // Never use them as ownership or persistence: a reload reads the API afresh.
  const removed = useRef(new Set<Meeting["id"]>())

  const readList = useCallback(async (signal?: AbortSignal) => {
    const generation = ++request.current
    const mutationAtStart = mutationGeneration.current
    const removedAtStart = new Set(removed.current)
    try {
      const result = await listMeetings(signal)
      if (!signal?.aborted && generation === request.current) {
        // If a deletion completed during this GET, reconcile against the newer
        // mutation generation rather than its stale snapshot. Keep other new rows.
        const excluded =
          mutationAtStart === mutationGeneration.current ? removedAtStart : removed.current
        setMeetings(result.filter((meeting) => !excluded.has(meeting.id)))
      }
    } catch {
      if (!signal?.aborted && generation === request.current)
        setError("Could not load meetings. Please try again.")
    } finally {
      if (!signal?.aborted && generation === request.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void readList(controller.signal)
    return () => controller.abort()
  }, [readList])

  async function load() {
    setLoading(true)
    setError("")
    await readList()
  }

  async function onCreated() {
    setSaved(true)
    await load()
  }

  async function onDelete(meeting: Meeting) {
    const result = await deleteMeeting(meeting.id)
    removed.current.add(meeting.id)
    mutationGeneration.current += 1
    setMeetings((current) => current.filter((item) => item.id !== meeting.id))
    setNotice(
      result === "deleted"
        ? `“${meeting.title}” deleted permanently.`
        : `“${meeting.title}” was already removed by another client.`,
    )
  }

  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  return (
    <div className="desktop">
      <div className="desk-window">
        <header className="window-titlebar">
          <span className="window-icon" aria-hidden="true">
            S
          </span>
          <span>Spry Meeting Desk</span>
          <span className="window-controls" aria-hidden="true">
            <span>―</span>
            <span>□</span>
            <span>×</span>
          </span>
        </header>
        <nav className="menu-strip" aria-label="Desk navigation">
          <a href="#appointments">Appointments</a>
          <a href="#new-meeting">New meeting</a>
          <a href="#desk-notes">Desk notes</a>
        </nav>
        <main>
          <div className="desk-banner">
            <div>
              <p className="eyebrow">A little more together</p>
              <h1>Meetings</h1>
              <p>Your next great conversation starts here.</p>
            </div>
            <div className="desk-stamp" aria-hidden="true">
              LET’S
              <br />
              GET TOGETHER!
            </div>
          </div>
          <div className="desk-layout">
            <aside className="desk-sidebar" aria-label="Desk overview">
              <h2>On your desk</h2>
              <dl className="desk-stats">
                <div>
                  <dt>Meetings listed</dt>
                  <dd>{meetings.length}</dd>
                </div>
                <div>
                  <dt>Attendee places</dt>
                  <dd>{meetings.reduce((sum, meeting) => sum + meeting.attendee_count, 0)}</dd>
                </div>
              </dl>
              <p className="sidebar-tip">
                Make a little time.
                <br />
                Make a big connection.
              </p>
              <p className="access-note">
                No accounts: anyone with API access can delete meetings.
              </p>
            </aside>
            <section
              id="appointments"
              aria-labelledby="list-heading"
              className="appointment-module"
            >
              <h2 id="list-heading" tabIndex={-1} className="module-heading">
                Your meetings <span>Appointment book</span>
              </h2>
              {saved && (
                <p role="status" className="desk-message">
                  {error
                    ? "Meeting created, but the list could not be refreshed. Retry loading the list; do not resubmit the meeting."
                    : "Meeting created successfully."}
                </p>
              )}
              <p role="status" className={notice ? "desk-message" : ""}>
                {notice}
              </p>
              {loading && (
                <p role="status" className="desk-message">
                  Loading meetings…
                </p>
              )}
              {error && (
                <div role="alert" className="desk-error">
                  <p>{error}</p>
                  <Button variant="outline" onClick={() => void load()}>
                    Retry loading
                  </Button>
                </div>
              )}
              {(meetings.length > 0 || (!loading && !error)) && (
                <MeetingList meetings={meetings} onDelete={onDelete} />
              )}
            </section>
            <section id="new-meeting" aria-label="Create a meeting" className="form-module">
              <MeetingForm onCreated={onCreated} />
            </section>
          </div>
        </main>
        <footer id="desk-notes" className="desk-footer">
          <span>All times are local · {timezone}</span>
          <span>Spry · Shared desk, no accounts</span>
        </footer>
      </div>
    </div>
  )
}
