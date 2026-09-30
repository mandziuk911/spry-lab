import { useCallback, useEffect, useState } from "react"
import { MeetingForm } from "@/components/MeetingForm"
import { MeetingList } from "@/components/MeetingList"
import { Button } from "@/components/ui/button"
import { listMeetings } from "@/lib/api"
import type { Meeting } from "@/types"

export default function App() {
  const [meetings, setMeetings] = useState<Meeting[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [saved, setSaved] = useState(false)

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true)
    setError("")
    try {
      const result = await listMeetings(signal)
      if (!signal?.aborted) setMeetings(result)
    } catch {
      if (!signal?.aborted) setError("Could not load meetings. Please try again.")
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void listMeetings(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setMeetings(result)
      })
      .catch(() => {
        if (!controller.signal.aborted) setError("Could not load meetings. Please try again.")
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [])

  async function onCreated() {
    setSaved(true)
    await load()
  }

  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  return (
    <div className="min-h-screen">
      <header className="border-b bg-card">
        <div className="mx-auto max-w-6xl px-6 py-5">
          <span className="text-2xl font-bold tracking-tight text-primary">
            spry<span className="text-foreground">.</span>
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-10 sm:py-14">
        <div className="mb-9">
          <p className="mb-2 text-xs font-semibold tracking-widest text-primary uppercase">
            A little more together
          </p>
          <h1 className="text-4xl font-semibold tracking-tight">Meetings</h1>
          <p className="mt-3 text-muted-foreground">
            Plan a conversation. Keep everyone on the same page.
          </p>
          <p className="mt-2 text-sm text-muted-foreground">All times are local · {timezone}</p>
        </div>
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section aria-labelledby="list-heading" className="min-w-0 space-y-4">
            <h2 id="list-heading" className="text-xl font-semibold">
              Your meetings
            </h2>
            {saved && (
              <p role="status" className="text-sm text-primary">
                {error
                  ? "Meeting created, but the list could not be refreshed. Retry loading the list; do not resubmit the meeting."
                  : "Meeting created successfully."}
              </p>
            )}
            {loading ? (
              <p role="status" className="py-10 text-muted-foreground">
                Loading meetings…
              </p>
            ) : error ? (
              <div role="alert" className="rounded-xl border border-destructive/30 bg-card p-6">
                <p className="mb-4 text-sm text-destructive">{error}</p>
                <Button variant="outline" onClick={() => void load()}>
                  Retry loading
                </Button>
              </div>
            ) : (
              <MeetingList meetings={meetings} />
            )}
          </section>
          <section aria-label="Create a meeting">
            <MeetingForm onCreated={onCreated} />
          </section>
        </div>
      </main>
    </div>
  )
}
