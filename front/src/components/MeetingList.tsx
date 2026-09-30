import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { Meeting } from "@/types"

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" })

export function MeetingList({ meetings }: { meetings: Meeting[] }) {
  if (!meetings.length)
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <h3 className="font-semibold">No meetings yet</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Create your first meeting to get started.
          </p>
        </CardContent>
      </Card>
    )
  return (
    <ul className="space-y-4" aria-label="Meetings">
      {meetings.map((meeting) => (
        <li key={meeting.id}>
          <Card>
            <CardHeader>
              <CardTitle>
                <h3 className="text-lg break-words">{meeting.title}</h3>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-4 text-sm sm:grid-cols-3">
                <div>
                  <dt className="text-muted-foreground">Start</dt>
                  <dd className="mt-1">
                    <time dateTime={meeting.starts_at}>
                      {dateFormat.format(new Date(meeting.starts_at))}
                    </time>
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">End</dt>
                  <dd className="mt-1">
                    <time dateTime={meeting.ends_at}>
                      {dateFormat.format(new Date(meeting.ends_at))}
                    </time>
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Attendees</dt>
                  <dd className="mt-1 font-semibold">{meeting.attendee_count}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  )
}
