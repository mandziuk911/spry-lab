import { useEffect, useId, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { loadAgenda, parseAgenda, saveAgenda } from "@/lib/api"
import { assertSession, useSession } from "@/lib/session"
import type { Meeting, ParsedAgenda, SavedAgenda } from "@/types"

const blank = (): SavedAgenda => ({
  title: null,
  starts_at: null,
  duration_minutes: null,
  items: [],
  action_items: [],
  language: "",
  ai_suggestion: null,
  ai_model: null,
  ai_prompt_version: null,
})
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T
function suggestedFields(agenda: ParsedAgenda) {
  const paths = new Set<string>()
  for (const key of ["title", "starts_at", "duration_minutes", "language"] as const) {
    if (agenda[key] !== null && agenda[key] !== "") paths.add(key)
  }
  for (const key of ["items", "action_items"] as const) {
    agenda[key].forEach((row, index) =>
      Object.entries(row).forEach(([field, value]) => {
        if (value !== null && value !== "") paths.add(`${key}.${index}.${field}`)
      }),
    )
  }
  return paths
}

export function MeetingAgenda({ meeting }: { meeting: Meeting }) {
  const session = useSession()
  const prefix = useId()
  const [agenda, setAgenda] = useState<SavedAgenda>(blank)
  const [badges, setBadges] = useState(new Set<string>())
  const [text, setText] = useState("")
  const [loading, setLoading] = useState(true)
  const [parsing, setParsing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const parser = useRef<AbortController | null>(null)
  const saveLock = useRef(false)
  const alive = useRef(false)

  useEffect(() => {
    alive.current = true
    const controller = new AbortController()
    void loadAgenda(session, meeting.id, controller.signal)
      .then((saved) => {
        if (!controller.signal.aborted) setAgenda(saved ? copy(saved) : blank())
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted)
          setError(
            failure instanceof Error && !(failure instanceof TypeError)
              ? failure.message
              : "Could not load the agenda. Check your connection. You can still enter it manually.",
          )
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => {
      alive.current = false
      controller.abort()
      parser.current?.abort()
      parser.current = null
    }
  }, [session, meeting.id])

  useEffect(() => {
    if (!parsing) return
    const timer = window.setInterval(() => setElapsed((seconds) => seconds + 1), 1000)
    return () => window.clearInterval(timer)
  }, [parsing])

  function cancel() {
    parser.current?.abort()
    parser.current = null
    setParsing(false)
  }

  function edited(path?: string) {
    // Editing also invalidates an in-flight parse, even if a transport ignores abort.
    cancel()
    setNotice("")
    if (path)
      setBadges((previous) => {
        const next = new Set(previous)
        next.delete(path)
        return next
      })
  }

  async function parse() {
    if (parser.current || saveLock.current) return
    setError("")
    setNotice("")
    if (!text.trim()) {
      setError("Paste an agenda first, or fill in the fields manually.")
      return
    }
    if (text.length > 10000) {
      setError("This agenda is too long. Shorten it to 10,000 characters or fewer.")
      return
    }
    const controller = new AbortController()
    parser.current = controller
    setElapsed(0)
    setParsing(true)
    try {
      const result = await parseAgenda(session, text, controller.signal)
      assertSession(session)
      if (parser.current !== controller || controller.signal.aborted || !alive.current) return
      const original = copy(result.agenda)
      setAgenda({
        ...copy(original),
        ai_suggestion: original,
        ai_model: result.model,
        ai_prompt_version: result.prompt_version,
      })
      setBadges(suggestedFields(original))
      setNotice("Suggestions ready. Review the fields, then save when you are ready.")
    } catch (failure) {
      if (parser.current === controller && !controller.signal.aborted && alive.current) {
        setError(
          failure instanceof Error
            ? failure.message
            : "The agenda reader failed. Enter the agenda manually.",
        )
      }
    } finally {
      if (parser.current === controller) {
        parser.current = null
        setParsing(false)
      }
    }
  }

  async function save() {
    if (saveLock.current || parser.current || loading) return
    saveLock.current = true
    setSaving(true)
    setError("")
    setNotice("")
    try {
      await saveAgenda(session, meeting.id, agenda)
      assertSession(session)
      if (alive.current) setNotice("Agenda saved.")
    } catch (failure) {
      if (alive.current)
        setError(
          failure instanceof Error && !(failure instanceof TypeError)
            ? failure.message
            : "Could not confirm the agenda was saved. Check your connection; your fields have been kept. Nothing was retried.",
        )
    } finally {
      saveLock.current = false
      if (alive.current) setSaving(false)
    }
  }

  function field(
    path: string,
    label: string,
    value: string | number | null,
    change: (value: string | number | null) => void,
    type = "text",
  ) {
    const id = `${prefix}-${path}`
    return (
      <div className="agenda-field" key={path}>
        <label htmlFor={id}>{label}</label>
        {badges.has(path) && <span className="suggested-badge">suggested</span>}
        <Input
          id={id}
          type={type}
          value={value ?? ""}
          min={type === "number" ? 0 : undefined}
          step={type === "number" ? 1 : undefined}
          placeholder={path === "starts_at" ? "2026-10-08T09:00:00+03:00" : undefined}
          onChange={(event) => {
            edited(path)
            change(
              event.target.value === ""
                ? null
                : type === "number"
                  ? Number(event.target.value)
                  : event.target.value,
            )
          }}
        />
      </div>
    )
  }

  function removeRow(key: "items" | "action_items", index: number) {
    edited()
    setAgenda((current) => ({ ...current, [key]: current[key].filter((_, i) => i !== index) }))
    setBadges(
      (previous) =>
        new Set(
          [...previous].flatMap((path) => {
            if (!path.startsWith(`${key}.`)) return [path]
            const [, row, name] = path.split(".")
            return Number(row) === index
              ? []
              : [`${key}.${Number(row) > index ? Number(row) - 1 : row}.${name}`]
          }),
        ),
    )
  }

  return (
    <section className="agenda-panel" aria-label={`Agenda for ${meeting.title}`}>
      <h4>Agenda · {meeting.title}</h4>
      {loading && <p role="status">Loading agenda…</p>}
      {error && (
        <p role="alert" className="desk-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="desk-message">
          {notice}
        </p>
      )}
      <fieldset disabled={loading || saving}>
        <legend>Paste an agenda</legend>
        <label htmlFor={`${prefix}-paste`}>Agenda text</label>
        <textarea
          id={`${prefix}-paste`}
          rows={5}
          value={text}
          onChange={(event) => {
            edited()
            setText(event.target.value)
          }}
        />
        <p>
          {text.length.toLocaleString()} / 10,000 characters. Parsing only suggests fields; it never
          saves.
        </p>
        <div className="confirm-actions">
          <Button type="button" onClick={() => void parse()} disabled={parsing || !text.trim()}>
            Parse
          </Button>
          {parsing && (
            <Button type="button" variant="outline" onClick={cancel}>
              Cancel
            </Button>
          )}
        </div>
        {parsing && <p role="status">Reading the agenda… {elapsed}s</p>}
      </fieldset>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void save()
        }}
      >
        <fieldset disabled={loading || saving}>
          <legend>Agenda details · edit manually at any time</legend>
          {field("title", "Agenda title", agenda.title, (value) =>
            setAgenda((current) => ({ ...current, title: value as string | null })),
          )}
          {field("starts_at", "Agenda start (ISO 8601 with timezone)", agenda.starts_at, (value) =>
            setAgenda((current) => ({ ...current, starts_at: value as string | null })),
          )}
          {field(
            "duration_minutes",
            "Duration (minutes)",
            agenda.duration_minutes,
            (value) =>
              setAgenda((current) => ({ ...current, duration_minutes: value as number | null })),
            "number",
          )}
          {field("language", "Language", agenda.language, (value) =>
            setAgenda((current) => ({ ...current, language: (value as string) ?? "" })),
          )}
          <h5>Agenda items</h5>
          {agenda.items.map((item, index) => (
            <div className="agenda-row" key={index}>
              {field(`items.${index}.topic`, `Item ${index + 1} topic`, item.topic, (value) =>
                setAgenda((current) => ({
                  ...current,
                  items: current.items.map((row, i) =>
                    i === index ? { ...row, topic: (value as string) ?? "" } : row,
                  ),
                })),
              )}
              {field(`items.${index}.owner`, `Item ${index + 1} owner`, item.owner, (value) =>
                setAgenda((current) => ({
                  ...current,
                  items: current.items.map((row, i) =>
                    i === index ? { ...row, owner: value as string | null } : row,
                  ),
                })),
              )}
              {field(
                `items.${index}.minutes`,
                `Item ${index + 1} minutes`,
                item.minutes,
                (value) =>
                  setAgenda((current) => ({
                    ...current,
                    items: current.items.map((row, i) =>
                      i === index ? { ...row, minutes: value as number | null } : row,
                    ),
                  })),
                "number",
              )}
              <Button type="button" variant="outline" onClick={() => removeRow("items", index)}>
                Remove item {index + 1}
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              edited()
              setAgenda((current) => ({
                ...current,
                items: [...current.items, { topic: "", owner: null, minutes: null }],
              }))
            }}
          >
            Add agenda item
          </Button>
          <h5>Action items</h5>
          {agenda.action_items.map((item, index) => (
            <div className="agenda-row" key={index}>
              {field(`action_items.${index}.task`, `Action ${index + 1} task`, item.task, (value) =>
                setAgenda((current) => ({
                  ...current,
                  action_items: current.action_items.map((row, i) =>
                    i === index ? { ...row, task: (value as string) ?? "" } : row,
                  ),
                })),
              )}
              {field(
                `action_items.${index}.owner`,
                `Action ${index + 1} owner`,
                item.owner,
                (value) =>
                  setAgenda((current) => ({
                    ...current,
                    action_items: current.action_items.map((row, i) =>
                      i === index ? { ...row, owner: value as string | null } : row,
                    ),
                  })),
              )}
              {field(
                `action_items.${index}.due`,
                `Action ${index + 1} due`,
                item.due,
                (value) =>
                  setAgenda((current) => ({
                    ...current,
                    action_items: current.action_items.map((row, i) =>
                      i === index ? { ...row, due: value as string | null } : row,
                    ),
                  })),
                "date",
              )}
              <Button
                type="button"
                variant="outline"
                onClick={() => removeRow("action_items", index)}
              >
                Remove action {index + 1}
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              edited()
              setAgenda((current) => ({
                ...current,
                action_items: [...current.action_items, { task: "", owner: null, due: null }],
              }))
            }}
          >
            Add action item
          </Button>
        </fieldset>
        <Button type="submit" disabled={loading || parsing || saving}>
          {saving ? "Saving agenda…" : "Save agenda"}
        </Button>
      </form>
    </section>
  )
}
