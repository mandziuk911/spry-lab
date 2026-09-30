import { useRef, useState } from "react"
import type { FormEvent } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { createMeeting } from "@/lib/api"

interface Props {
  onCreated: () => Promise<void>
}

export function MeetingForm({ onCreated }: Props) {
  const [title, setTitle] = useState("")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [count, setCount] = useState("0")
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const locked = useRef(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (locked.current) return
    setError("")
    const startsAt = new Date(start)
    const endsAt = new Date(end)
    const attendees = Number(count)
    if (!title.trim() || title.trim().length > 200) {
      setError("Enter a title between 1 and 200 characters.")
      return
    }
    if (
      !start ||
      !end ||
      !Number.isFinite(startsAt.getTime()) ||
      !Number.isFinite(endsAt.getTime()) ||
      endsAt <= startsAt
    ) {
      setError("Choose valid dates with the end after the start.")
      return
    }
    if (!/^\d+$/.test(count) || !Number.isSafeInteger(attendees) || attendees < 0) {
      setError("Attendee count must be a whole number of zero or more.")
      return
    }
    locked.current = true
    setSubmitting(true)
    try {
      await createMeeting({
        title: title.trim(),
        starts_at: startsAt.toISOString(),
        ends_at: endsAt.toISOString(),
        attendee_count: attendees,
      })
    } catch {
      setError(
        "Could not create the meeting. Check your details and connection. Your details have been kept.",
      )
      locked.current = false
      setSubmitting(false)
      return
    }
    setTitle("")
    setStart("")
    setEnd("")
    setCount("0")
    // Refresh handles its own errors: a saved meeting must never be reported as a failed POST.
    try {
      await onCreated()
    } finally {
      locked.current = false
      setSubmitting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-xl">New meeting</h2>
        </CardTitle>
        <CardDescription>Make room for your next conversation.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} noValidate className="space-y-5">
          <fieldset disabled={submitting} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                placeholder="Design catch-up"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="start">Start</Label>
              <Input
                id="start"
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="end">End</Label>
              <Input
                id="end"
                type="datetime-local"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="count">Attendee count</Label>
              <Input
                id="count"
                type="number"
                min="0"
                step="1"
                value={count}
                onChange={(e) => setCount(e.target.value)}
                required
              />
            </div>
          </fieldset>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Saving…" : "Create meeting"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
