export interface Meeting {
  id: string
  title: string
  starts_at: string
  ends_at: string
  attendee_count: number
}

export type CreateMeeting = Omit<Meeting, "id">

export interface ParsedAgenda {
  title: string | null
  starts_at: string | null
  duration_minutes: number | null
  items: { topic: string; owner: string | null; minutes: number | null }[]
  action_items: { task: string; owner: string | null; due: string | null }[]
  language: string
}

export interface SavedAgenda extends ParsedAgenda {
  ai_suggestion: ParsedAgenda | null
  ai_model: string | null
  ai_prompt_version: string | null
}

export interface AgendaSuggestion {
  agenda: ParsedAgenda
  model: string
  prompt_version: string
}
