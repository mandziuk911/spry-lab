import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import App from "@/App"
import { MeetingForm } from "@/components/MeetingForm"

const meeting = {
  id: "7b96c369-22af-4c3e-88d5-e2d447552c7f",
  title: "Team sync",
  starts_at: "2026-08-10T09:00:00Z",
  ends_at: "2026-08-10T10:00:00Z",
  attendee_count: 4,
}
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
function fill(title = "  Team sync  ", end = "2026-08-10T10:00", count = "4") {
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: title } })
  fireEvent.change(screen.getByLabelText("Start"), { target: { value: "2026-08-10T09:00" } })
  fireEvent.change(screen.getByLabelText("End"), { target: { value: end } })
  fireEvent.change(screen.getByLabelText("Attendee count"), { target: { value: count } })
}

describe("meeting page", () => {
  it("distinguishes loading and empty states", async () => {
    let resolve!: (value: Response) => void
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((r) => {
            resolve = r
          }),
      ),
    )
    render(<App />)
    expect(screen.getByText("Loading meetings…")).toBeInTheDocument()
    expect(screen.queryByText("No meetings yet")).not.toBeInTheDocument()
    resolve(json([]))
    expect(await screen.findByText("No meetings yet")).toBeInTheDocument()
    expect(screen.getByText(/All times are local/)).toBeInTheDocument()
  })

  it("renders the exact contract and calls the configured API", async () => {
    vi.stubEnv("VITE_API_URL", "http://localhost:9000/")
    const fetch = vi.fn().mockResolvedValue(json([meeting]))
    vi.stubGlobal("fetch", fetch)
    render(<App />)
    expect(await screen.findByRole("heading", { name: "Team sync" })).toBeInTheDocument()
    expect(screen.getByText("4")).toBeInTheDocument()
    expect(document.querySelectorAll("time")).toHaveLength(2)
    expect(document.querySelector("time")).toHaveAttribute("datetime", meeting.starts_at)
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:9000/api/meetings",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })

  it("shows GET errors rather than an empty list and supports retry", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({}, 503)).mockResolvedValueOnce(json([]))
    vi.stubGlobal("fetch", fetch)
    render(<App />)
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load")
    expect(screen.queryByText("No meetings yet")).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Retry loading" }))
    expect(await screen.findByText("No meetings yet")).toBeInTheDocument()
  })

  it("trims, converts local dates to UTC, sends only four fields and refreshes after 201", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(json([]))
      .mockResolvedValueOnce(json(meeting, 201))
      .mockResolvedValueOnce(json([meeting]))
    vi.stubGlobal("fetch", fetch)
    render(<App />)
    await screen.findByText("No meetings yet")
    fill()
    await userEvent.click(screen.getByRole("button", { name: "Create meeting" }))
    expect(await screen.findByRole("heading", { name: "Team sync" })).toBeInTheDocument()
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
      title: "Team sync",
      starts_at: new Date("2026-08-10T09:00").toISOString(),
      ends_at: new Date("2026-08-10T10:00").toISOString(),
      attendee_count: 4,
    })
    expect(fetch.mock.calls[1][1].method).toBe("POST")
    expect(screen.getByLabelText("Title")).toHaveValue("")
    expect(screen.getByLabelText("Attendee count")).toHaveValue(0)
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it.each([422, 503])(
    "preserves input after POST %s and does not retry or refresh",
    async (status) => {
      const fetch = vi.fn().mockResolvedValue(json({}, status))
      vi.stubGlobal("fetch", fetch)
      render(<MeetingForm onCreated={vi.fn()} />)
      fill()
      await userEvent.click(screen.getByRole("button", { name: "Create meeting" }))
      expect(await screen.findByRole("alert")).toHaveTextContent("details have been kept")
      expect(screen.getByLabelText("Title")).toHaveValue("  Team sync  ")
      expect(screen.getByLabelText("Start")).toHaveValue("2026-08-10T09:00")
      expect(screen.getByLabelText("End")).toHaveValue("2026-08-10T10:00")
      expect(screen.getByLabelText("Attendee count")).toHaveValue(4)
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )

  it("distinguishes successful creation from failed list refresh", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(json([]))
      .mockResolvedValueOnce(json(meeting, 201))
      .mockRejectedValueOnce(new TypeError("offline"))
    vi.stubGlobal("fetch", fetch)
    render(<App />)
    await screen.findByText("No meetings yet")
    fill()
    await userEvent.click(screen.getByRole("button", { name: "Create meeting" }))
    expect(await screen.findByText(/Meeting created, but/)).toBeInTheDocument()
    expect(screen.getByLabelText("Title")).toHaveValue("")
    expect(screen.queryByText(/Could not create/)).not.toBeInTheDocument()
  })

  it("disables duplicate submissions while POST is pending", async () => {
    let resolve!: (value: Response) => void
    const fetch = vi.fn(
      () =>
        new Promise<Response>((r) => {
          resolve = r
        }),
    )
    vi.stubGlobal("fetch", fetch)
    const onCreated = vi.fn().mockResolvedValue(undefined)
    render(<MeetingForm onCreated={onCreated} />)
    fill()
    const button = screen.getByRole("button", { name: "Create meeting" })
    await userEvent.dblClick(button)
    expect(button).toBeDisabled()
    expect(screen.getByLabelText("Title")).toBeDisabled()
    expect(fetch).toHaveBeenCalledTimes(1)
    resolve(json(meeting, 201))
    await waitFor(() => expect(button).not.toBeDisabled())
    expect(onCreated).toHaveBeenCalledTimes(1)
  })

  it.each([
    ["   ", "2026-08-10T10:00", "0", "Enter a title"],
    ["x".repeat(201), "2026-08-10T10:00", "0", "Enter a title"],
    ["Sync", "2026-08-10T09:00", "0", "end after the start"],
    ["Sync", "", "0", "valid dates"],
    ["Sync", "2026-08-10T10:00", "-1", "whole number"],
    ["Sync", "2026-08-10T10:00", "1.5", "whole number"],
    ["Sync", "2026-08-10T10:00", "", "whole number"],
  ])(
    "validates invalid form values before POST (%s, %s, %s)",
    async (title, end, count, message) => {
      const fetch = vi.fn()
      vi.stubGlobal("fetch", fetch)
      render(<MeetingForm onCreated={vi.fn()} />)
      fill(title, end, count)
      await userEvent.click(screen.getByRole("button", { name: "Create meeting" }))
      expect(screen.getByRole("alert")).toHaveTextContent(message)
      expect(fetch).not.toHaveBeenCalled()
    },
  )
})
