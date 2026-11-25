import "@/test/authFixture"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { MeetingAgenda } from "@/components/MeetingAgenda"
import { MeetingList } from "@/components/MeetingList"
import { loadAgenda, parseAgenda, saveAgenda } from "@/lib/api"
import { SessionLifetime, useSession } from "@/lib/session"
import type { ParsedAgenda } from "@/types"

const meeting = {
  id: "meeting-id",
  title: "Team sync",
  starts_at: "2026-10-10T09:00:00Z",
  ends_at: "2026-10-10T10:00:00Z",
  attendee_count: 2,
}
const suggestion: ParsedAgenda = {
  title: "Planning",
  starts_at: "2026-10-10T09:00:00+03:00",
  duration_minutes: 30,
  items: [{ topic: "Roadmap", owner: "Pat", minutes: 20 }],
  action_items: [{ task: "Send notes", owner: "Sam", due: "2026-10-11" }],
  language: "en",
}
const result = { agenda: suggestion, model: "test-model", prompt_version: "v1" }
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
const missing = () => json({ detail: "Agenda not found" }, 404)
const deferred = <T,>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}
function change(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}
async function mount() {
  const view = render(<MeetingAgenda meeting={meeting} />)
  await waitFor(() => expect(screen.getByRole("button", { name: "Save agenda" })).toBeEnabled())
  return view
}
function start() {
  change("Agenda text", "Tomorrow: planning and notes")
  fireEvent.click(screen.getByRole("button", { name: "Parse" }))
}

describe("agenda editor", () => {
  beforeEach(() => vi.stubEnv("VITE_PARSER_URL", "https://parser.example/parse"))
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  it("opens a named meeting panel only on demand", async () => {
    const fetch = vi.fn().mockResolvedValue(missing())
    vi.stubGlobal("fetch", fetch)
    render(<MeetingList meetings={[meeting]} now={0} hiddenCount={0} onDelete={vi.fn()} />)
    expect(fetch).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "Agenda for Team sync" }))
    expect(await screen.findByRole("region", { name: "Agenda for Team sync" })).toHaveTextContent(
      "Agenda · Team sync",
    )
    await waitFor(() => expect(screen.getByRole("button", { name: "Save agenda" })).toBeEnabled())
  })

  it("fills every field, clears only edited badges, and saves the immutable original to the main API", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(missing())
      .mockResolvedValueOnce(json(result))
      .mockResolvedValueOnce(json({}))
    vi.stubGlobal("fetch", fetch)
    await mount()
    start()
    await screen.findByText(/Suggestions ready/)
    expect(screen.getAllByText("suggested")).toHaveLength(10)
    expect(screen.getByLabelText("Agenda start (ISO 8601 with timezone)")).toHaveValue(
      suggestion.starts_at,
    )
    expect(screen.getByLabelText("Action 1 due")).toHaveValue("2026-10-11")
    change("Agenda title", "Edited title")
    expect(
      within(screen.getByLabelText("Agenda title").parentElement!).queryByText("suggested"),
    ).not.toBeInTheDocument()
    change("Item 1 owner", "Alex")
    expect(screen.getAllByText("suggested")).toHaveLength(8)
    expect(
      within(screen.getByLabelText("Item 1 topic").parentElement!).getByText("suggested"),
    ).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2) // Parse never saves.
    const [url, options] = fetch.mock.calls[1]
    expect(url).toBe("https://parser.example/parse")
    expect(options).toMatchObject({
      credentials: "omit",
      headers: { Authorization: "Bearer fixture-access" },
    })
    const now = new Date()
    expect(JSON.parse(options.body)).toEqual({
      text: "Tomorrow: planning and notes",
      today: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`,
      tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    })
    fireEvent.click(screen.getByRole("button", { name: "Save agenda" }))
    await screen.findByText("Agenda saved.")
    expect(fetch.mock.calls[2][0]).toContain(`/api/meetings/${meeting.id}/agenda`)
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({
      ...suggestion,
      title: "Edited title",
      items: [{ ...suggestion.items[0], owner: "Alex" }],
      ai_suggestion: suggestion,
      ai_model: "test-model",
      ai_prompt_version: "v1",
    })
  })

  it("cancels elapsed progress, ignores a late response, and does not clobber a subsequent parse", async () => {
    const old = deferred<Response>()
    const next = deferred<Response>()
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(missing())
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(next.promise)
    vi.stubGlobal("fetch", fetch)
    await mount()
    vi.useFakeTimers()
    start()
    expect(screen.getByRole("button", { name: "Save agenda" })).toBeDisabled()
    act(() => vi.advanceTimersByTime(3000))
    expect(screen.getByText("Reading the agenda… 3s")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(fetch.mock.calls[1][1].signal.aborted).toBe(true)
    change("Agenda title", "Keep this edit")
    fireEvent.click(screen.getByRole("button", { name: "Parse" }))
    await act(async () => {
      old.resolve(json(result))
    })
    expect(screen.getByLabelText("Agenda title")).toHaveValue("Keep this edit")
    expect(screen.getByText("Reading the agenda… 0s")).toBeInTheDocument()
    await act(async () => {
      next.resolve(json({ ...result, agenda: { ...suggestion, title: "Fresh result" } }))
    })
    expect(screen.getByLabelText("Agenda title")).toHaveValue("Fresh result")
    expect(screen.queryByText(/Reading the agenda/)).not.toBeInTheDocument()
    expect(vi.getTimerCount()).toBe(0)
  })

  it("aborts on unmount and editing invalidates a pending parse", async () => {
    const pending = deferred<Response>()
    const fetch = vi.fn().mockResolvedValueOnce(missing()).mockReturnValue(pending.promise)
    vi.stubGlobal("fetch", fetch)
    const view = await mount()
    start()
    change("Agenda title", "Manual edit")
    expect(fetch.mock.calls[1][1].signal.aborted).toBe(true)
    await act(async () => pending.resolve(json(result)))
    expect(screen.getByLabelText("Agenda title")).toHaveValue("Manual edit")
    const late = deferred<Response>()
    fetch.mockReturnValue(late.promise)
    fireEvent.click(screen.getByRole("button", { name: "Parse" }))
    view.unmount()
    expect(fetch.mock.calls[2][1].signal.aborted).toBe(true)
    await act(async () => late.resolve(json(result)))
  })

  it.each([
    [413, /too long/],
    [422, /could not be read/],
    [429, /limit was reached/],
    [401, /session ended/],
    [502, /temporarily unavailable/],
    [0, /Check your connection/],
  ])(
    "explains parser failure %s without retrying and retains manual input",
    async (status, message) => {
      const fetch = vi.fn().mockResolvedValueOnce(missing())
      if (status) fetch.mockResolvedValueOnce(json({}, status as number))
      else fetch.mockRejectedValueOnce(new TypeError("offline"))
      vi.stubGlobal("fetch", fetch)
      await mount()
      change("Agenda title", "Keep me")
      start()
      expect(await screen.findByRole("alert")).toHaveTextContent(message as RegExp)
      expect(screen.getByLabelText("Agenda title")).toHaveValue("Keep me")
      expect(screen.getByRole("button", { name: "Save agenda" })).toBeEnabled()
      expect(fetch).toHaveBeenCalledTimes(2)
    },
  )

  it("explains missing configuration and the local character limit without a parser call", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(missing())
    vi.stubGlobal("fetch", fetch)
    vi.stubEnv("VITE_PARSER_URL", "")
    await mount()
    start()
    expect(await screen.findByRole("alert")).toHaveTextContent("not configured")
    change("Agenda text", "x".repeat(10001))
    fireEvent.click(screen.getByRole("button", { name: "Parse" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("10,000 characters")
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it("saves manually added rows without AI metadata and blocks duplicate saves", async () => {
    const saved = deferred<Response>()
    const fetch = vi.fn().mockResolvedValueOnce(missing()).mockReturnValueOnce(saved.promise)
    vi.stubGlobal("fetch", fetch)
    await mount()
    change("Agenda title", "Manual")
    fireEvent.click(screen.getByRole("button", { name: "Add agenda item" }))
    change("Item 1 topic", "Topic")
    change("Item 1 minutes", "0")
    fireEvent.click(screen.getByRole("button", { name: "Add action item" }))
    change("Action 1 task", "Follow up")
    const save = screen.getByRole("button", { name: "Save agenda" })
    fireEvent.click(save)
    fireEvent.click(save)
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({
      title: "Manual",
      starts_at: null,
      duration_minutes: null,
      items: [{ topic: "Topic", owner: null, minutes: 0 }],
      action_items: [{ task: "Follow up", owner: null, due: null }],
      ai_suggestion: null,
      ai_model: null,
      ai_prompt_version: null,
    })
    await act(async () => saved.resolve(json({})))
    expect(screen.getByText("Agenda saved.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Remove item 1" }))
    fireEvent.click(screen.getByRole("button", { name: "Remove action 1" }))
    expect(screen.queryByLabelText("Item 1 topic")).not.toBeInTheDocument()
    expect(screen.queryByLabelText("Action 1 task")).not.toBeInTheDocument()
  })

  it.each([422, 502, 0])(
    "keeps manual fields after save failure %s without retrying",
    async (status) => {
      const fetch = vi.fn().mockResolvedValueOnce(missing())
      if (status) fetch.mockResolvedValueOnce(json({}, status))
      else fetch.mockRejectedValueOnce(new TypeError("offline"))
      vi.stubGlobal("fetch", fetch)
      await mount()
      change("Agenda title", "Keep my manual agenda")
      fireEvent.click(screen.getByRole("button", { name: "Save agenda" }))
      await screen.findByRole("alert")
      expect(screen.getByLabelText("Agenda title")).toHaveValue("Keep my manual agenda")
      expect(screen.getByRole("button", { name: "Save agenda" })).toBeEnabled()
      expect(fetch).toHaveBeenCalledTimes(2)
      expect(screen.queryByText("Agenda saved.")).not.toBeInTheDocument()
    },
  )

  it.each([{}, { ...result, agenda: { ...suggestion, items: null } }])(
    "treats malformed parser success as an unavailable reader, preserving manual fallback",
    async (body) => {
      const fetch = vi.fn().mockResolvedValueOnce(missing()).mockResolvedValueOnce(json(body))
      vi.stubGlobal("fetch", fetch)
      await mount()
      change("Agenda title", "Manual fallback")
      start()
      expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable")
      expect(screen.getByLabelText("Agenda title")).toHaveValue("Manual fallback")
      expect(fetch).toHaveBeenCalledTimes(2)
    },
  )

  it("restores a saved agenda and distinguishes an unknown meeting from a blank agenda", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        json({ ...suggestion, ai_suggestion: suggestion, ai_model: "m", ai_prompt_version: "v" }),
      )
      .mockResolvedValueOnce(json({ detail: "Meeting not found" }, 404))
    vi.stubGlobal("fetch", fetch)
    const view = await mount()
    expect(screen.getByLabelText("Agenda title")).toHaveValue("Planning")
    view.unmount()
    await mount()
    expect(screen.getByRole("alert")).toHaveTextContent("Meeting not found")
  })
})

describe("agenda client session boundaries", () => {
  it("does not clear the meeting creation draft on an agenda 200", async () => {
    const session = useSession()
    const draft = "creation draft"
    sessionStorage.setItem(session.key, draft)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({})))
    await saveAgenda(session, meeting.id, {
      ...suggestion,
      ai_suggestion: null,
      ai_model: null,
      ai_prompt_version: null,
    })
    expect(sessionStorage.getItem(session.key)).toBe(draft)
  })

  it("expires on parser 401 and blocks a response after session invalidation", async () => {
    vi.stubEnv("VITE_PARSER_URL", "https://parser.example")
    const session = useSession()
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 401)))
    await expect(parseAgenda(session, "text", new AbortController().signal)).rejects.toThrow(
      /session ended/,
    )
    expect(session.expire).toHaveBeenCalledTimes(1)
    const lifetime = new SessionLifetime(session.key, session.email, session.user, vi.fn(), vi.fn())
    const pending = deferred<Response>()
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending.promise))
    const promise = parseAgenda(lifetime, "text", new AbortController().signal)
    lifetime.invalidate()
    pending.resolve(json(result))
    await expect(promise).rejects.toThrow(/Session ended/)
    vi.unstubAllEnvs()
  })

  it("rechecks the session after reading the saved agenda body", async () => {
    const session = useSession()
    const lifetime = new SessionLifetime(session.key, session.email, session.user, vi.fn(), vi.fn())
    const body = deferred<unknown>()
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 200, json: () => body.promise }))
    const promise = loadAgenda(lifetime, meeting.id)
    await act(async () => {})
    lifetime.invalidate()
    body.resolve(suggestion)
    await expect(promise).rejects.toThrow(/Session ended/)
  })
})
