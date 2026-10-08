import "@/test/authFixture"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import App from "@/App"
import { isMeetingVisible, meetingStatus } from "@/lib/meetingStatus"

const meeting = {
  id: "7b96c369-22af-4c3e-88d5-e2d447552c7f",
  title: "Clock sync",
  starts_at: "2026-10-01T09:00:00Z",
  ends_at: "2026-10-01T10:00:00Z",
  attendee_count: 4,
}

it.each([
  ["2026-10-01T08:59:59.999Z", "scheduled", true],
  ["2026-10-01T09:00:00Z", "in-progress", true],
  ["2026-10-01T09:59:59.999Z", "in-progress", true],
  ["2026-10-01T10:00:00Z", "finished", true],
  ["2026-10-01T10:59:59.999Z", "finished", true],
  ["2026-10-01T11:00:00Z", "finished", false],
  ["2026-10-01T11:00:00.001Z", "finished", false],
])("classifies the exact boundary %s", (timestamp, status, visible) => {
  const now = Date.parse(timestamp)
  expect(meetingStatus(meeting, now)).toBe(status)
  expect(isMeetingVisible(meeting, now)).toBe(visible)
})

it("compares absolute timestamps across local midnight and timezone offsets", () => {
  const overnight = {
    ...meeting,
    starts_at: "2026-10-01T23:50:00+03:00",
    ends_at: "2026-10-02T00:10:00+03:00",
  }
  expect(meetingStatus(overnight, Date.parse("2026-10-01T21:05:00Z"))).toBe("in-progress")
  expect(meetingStatus(overnight, Date.parse("2026-10-01T21:10:00Z"))).toBe("finished")
  expect(isMeetingVisible(overnight, Date.parse("2026-10-01T22:10:00Z"))).toBe(false)
})

it("measures one real hour across the daylight-saving fallback", () => {
  const fallback = {
    ...meeting,
    starts_at: "2026-11-01T01:30:00-04:00",
    ends_at: "2026-11-01T01:30:00-05:00",
  }
  expect(meetingStatus(fallback, Date.parse("2026-11-01T06:00:00Z"))).toBe("in-progress")
  expect(isMeetingVisible(fallback, Date.parse("2026-11-01T07:29:59.999Z"))).toBe(true)
  expect(isMeetingVisible(fallback, Date.parse("2026-11-01T07:30:00Z"))).toBe(false)
})

describe("live meeting clock", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-10-01T08:59:59Z"))
  })

  async function open(meetings = [meeting]) {
    const fetch = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify(meetings), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    )
    vi.stubGlobal("fetch", fetch)
    let view!: ReturnType<typeof render>
    await act(async () => {
      view = render(<App />)
    })
    return { fetch, view }
  }

  it("updates all statuses, hides after one hour, preserves drafts and sends no mutation", async () => {
    const { fetch } = await open()
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Keep my draft" } })
    expect(screen.getByText("Scheduled", { exact: true })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: meeting.title }).closest("li")).toHaveClass(
      "appointment-scheduled",
    )
    act(() => vi.advanceTimersByTime(1000))
    expect(screen.getByText("In progress", { exact: true })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: meeting.title }).closest("li")).toHaveClass(
      "appointment-in-progress",
    )
    act(() => vi.advanceTimersByTime(60 * 60 * 1000))
    expect(screen.getByText("Finished", { exact: true })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: meeting.title }).closest("li")).toHaveClass(
      "appointment-finished",
    )
    act(() => vi.advanceTimersByTime(60 * 60 * 1000 - 1))
    expect(screen.getByRole("heading", { name: meeting.title })).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1))
    expect(screen.queryByRole("heading", { name: meeting.title })).not.toBeInTheDocument()
    expect(screen.getByText("No current meetings")).toBeInTheDocument()
    expect(screen.getByText("Meetings listed").parentElement).toHaveTextContent("0")
    expect(screen.getByText("Attendee places").parentElement).toHaveTextContent("0")
    expect(screen.getByLabelText("Title")).toHaveValue("Keep my draft")
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it.each(["focus", "visibilitychange"])(
    "resynchronizes immediately on %s without fetching or losing hidden records",
    async (event) => {
      const { fetch } = await open()
      act(() => {
        vi.setSystemTime(new Date("2026-10-01T11:00:00Z"))
        ;(event === "focus" ? window : document).dispatchEvent(new Event(event))
      })
      expect(screen.getByText("No current meetings")).toBeInTheDocument()
      act(() => {
        vi.setSystemTime(new Date("2026-10-01T09:30:00Z"))
        ;(event === "focus" ? window : document).dispatchEvent(new Event(event))
      })
      expect(screen.getByRole("heading", { name: meeting.title })).toBeInTheDocument()
      expect(screen.getByText("In progress", { exact: true })).toBeInTheDocument()
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )

  it("keeps expired rows hidden after a fresh mount and repeated GET", async () => {
    vi.setSystemTime(new Date("2026-10-01T11:00:00Z"))
    const first = await open()
    expect(screen.getByText("No current meetings")).toBeInTheDocument()
    first.view.unmount()
    const second = await open()
    expect(screen.getByText("No current meetings")).toBeInTheDocument()
    expect(second.fetch).toHaveBeenCalledTimes(1)
    expect(meeting.title).toBe("Clock sync")
  })

  it("distinguishes an empty API response from hidden finished meetings", async () => {
    await open([])
    expect(screen.getByText("No meetings yet")).toBeInTheDocument()
    expect(screen.queryByText("No current meetings")).not.toBeInTheDocument()
  })

  it("cleans up its interval and focus/visibility listeners on unmount", async () => {
    const removeWindow = vi.spyOn(window, "removeEventListener")
    const removeDocument = vi.spyOn(document, "removeEventListener")
    const { view } = await open()
    expect(vi.getTimerCount()).toBe(1)
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
    expect(removeWindow).toHaveBeenCalledWith("focus", expect.any(Function))
    expect(removeDocument).toHaveBeenCalledWith("visibilitychange", expect.any(Function))
  })
})
