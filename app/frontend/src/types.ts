export type Intent = 'qa' | 'explain' | 'lesson'

export interface Citation {
  ref: string
  text_he: string
  text_en: string
  commentator: string
  deep_link: string
}

export interface Message {
  id?: number
  role: 'user' | 'assistant'
  text: string
  intent?: Intent
  citations: Citation[]
  caveats: string[]
  grounded?: boolean
  created_at?: string
}

export interface Session {
  id: string
  first_q: string
  created_at: string
}

export interface QueryResponse {
  answer: string
  citations: Citation[]
  grounded: boolean
  intent: Intent
  caveats: string[]
  session_id?: string
}
