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
  it("cancels a named permanent deletion without a request", async () => {
    const fetch = vi.fn().mockResolvedValue(json([meeting]))
    vi.stubGlobal("fetch", fetch)
    render(<App />)
    await screen.findByRole("heading", { name: meeting.title })
    await userEvent.click(screen.getByRole("button", { name: "Delete Team sync" }))
    expect(screen.getByRole("group", { name: "Confirm deletion of Team sync" })).toHaveTextContent(
      "permanent",
    )
    expect(screen.getByRole("button", { name: "Cancel deletion" })).toHaveFocus()
    await userEvent.click(screen.getByRole("button", { name: "Cancel deletion" }))
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Delete Team sync" })).toHaveFocus(),
    )
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("heading", { name: meeting.title })).toBeInTheDocument()
  })

  it.each([204, 404])(
    "removes a meeting on %s without parsing a body or refreshing, preserving the form",
    async (status) => {
      const response = new Response(null, { status })
      const parse = vi.spyOn(response, "json")
      const fetch = vi
        .fn()
        .mockResolvedValueOnce(json([meeting]))
        .mockResolvedValueOnce(response)
      vi.stubGlobal("fetch", fetch)
      render(<App />)
      await screen.findByRole("heading", { name: meeting.title })
      fill("Unfinished draft")
      await userEvent.click(screen.getByRole("button", { name: "Delete Team sync" }))
      await userEvent.click(screen.getByRole("button", { name: "Permanently delete meeting" }))
      expect(
        await screen.findByText(
          status === 204 ? /deleted permanently/ : /already removed by another client/,
        ),
      ).toBeInTheDocument()
      expect(screen.queryByRole("heading", { name: meeting.title })).not.toBeInTheDocument()
      expect(screen.getByLabelText("Title")).toHaveValue("Unfinished draft")
      expect(screen.getByLabelText("Start")).toHaveValue("2026-08-10T09:00")
      expect(screen.getByLabelText("End")).toHaveValue("2026-08-10T10:00")
      expect(screen.getByLabelText("Attendee count")).toHaveValue(4)
      expect(fetch).toHaveBeenCalledTimes(2)
      expect(fetch.mock.calls[1]).toEqual([
        expect.stringContaining(`/api/meetings/${meeting.id}`),
        { method: "DELETE" },
      ])
      expect(parse).not.toHaveBeenCalled()
      expect(screen.getByRole("heading", { name: /Your meetings/ })).toHaveFocus()
    },
  )

  it.each(["503", "network"])(
    "retains the meeting and input after %s deletion failure with no automatic retry",
    async (failure) => {
      const fetch = vi.fn().mockResolvedValueOnce(json([meeting]))
      if (failure === "503") fetch.mockResolvedValueOnce(json({}, 503))
      else fetch.mockRejectedValueOnce(new TypeError("offline"))
      vi.stubGlobal("fetch", fetch)
      render(<App />)
      await screen.findByRole("heading", { name: meeting.title })
      fill("Keep this draft")
      await userEvent.click(screen.getByRole("button", { name: "Delete Team sync" }))
      await userEvent.click(screen.getByRole("button", { name: "Permanently delete meeting" }))
      expect(await screen.findByRole("alert")).toHaveTextContent("Could not delete")
      expect(screen.getByRole("heading", { name: meeting.title })).toBeInTheDocument()
      expect(screen.getByLabelText("Title")).toHaveValue("Keep this draft")
      expect(screen.getByRole("button", { name: "Permanently delete meeting" })).toBeEnabled()
      expect(fetch).toHaveBeenCalledTimes(2)
    },
  )

  it("locks repeated confirmations while deletion is pending", async () => {
    let resolve!: (response: Response) => void
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(json([meeting]))
      .mockImplementationOnce(
        () =>
          new Promise<Response>((r) => {
            resolve = r
          }),
      )
    vi.stubGlobal("fetch", fetch)
    render(<App />)
    await screen.findByRole("heading", { name: meeting.title })
    await userEvent.click(screen.getByRole("button", { name: "Delete Team sync" }))
    const confirm = screen.getByRole("button", { name: "Permanently delete meeting" })
    await userEvent.dblClick(confirm)
    fireEvent.click(confirm)
    expect(confirm).toBeDisabled()
    expect(screen.getByRole("button", { name: "Cancel deletion" })).toBeDisabled()
    expect(fetch).toHaveBeenCalledTimes(2)
    resolve(new Response(null, { status: 204 }))
    expect(await screen.findByText(/deleted permanently/)).toBeInTheDocument()
  })

  it.each(["refresh-first", "delete-first"])(
    "does not resurrect a deleted meeting from a stale creation refresh (%s)",
    async (order) => {
      let resolveRefresh!: (response: Response) => void
      let resolveDelete!: (response: Response) => void
      const fetch = vi
        .fn()
        .mockResolvedValueOnce(json([meeting]))
        .mockResolvedValueOnce(json(meeting, 201))
        .mockImplementationOnce(
          () =>
            new Promise<Response>((r) => {
              resolveRefresh = r
            }),
        )
        .mockImplementationOnce(
          () =>
            new Promise<Response>((r) => {
              resolveDelete = r
            }),
        )
      vi.stubGlobal("fetch", fetch)
      render(<App />)
      await screen.findByRole("heading", { name: meeting.title })
      fill("New appointment")
      await userEvent.click(screen.getByRole("button", { name: "Create meeting" }))
      await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
      await userEvent.click(screen.getByRole("button", { name: "Delete Team sync" }))
      await userEvent.click(screen.getByRole("button", { name: "Permanently delete meeting" }))
      if (order === "refresh-first") {
        resolveRefresh(json([meeting]))
        await waitFor(() => expect(screen.queryByText("Loading meetings…")).not.toBeInTheDocument())
        resolveDelete(new Response(null, { status: 204 }))
      } else {
        resolveDelete(new Response(null, { status: 204 }))
        await screen.findByText(/deleted permanently/)
        resolveRefresh(json([meeting]))
      }
      expect(await screen.findByText("No meetings yet")).toBeInTheDocument()
      expect(screen.queryByRole("heading", { name: meeting.title })).not.toBeInTheDocument()
      expect(fetch).toHaveBeenCalledTimes(4)
    },
  )

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
    expect(screen.getAllByText("4")).toHaveLength(2)
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
