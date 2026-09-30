export interface Meeting {
  id: string
  title: string
  starts_at: string
  ends_at: string
  attendee_count: number
}

export type CreateMeeting = Omit<Meeting, "id">
