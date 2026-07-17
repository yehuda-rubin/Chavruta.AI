// Mirrors the FastAPI response shapes (app/api.py). The active static UI is the behavioural
// source of truth; these types match what /query, /sessions, /lessons actually return.

export type Intent = "qa" | "explain" | "compare" | "halacha" | "lesson";

export interface Citation {
  ref: string;
  text_he: string;
  text_en: string;
  commentator: string;
  deep_link: string;
  // Rights of the edition this text came from (populated after the licence backfill). CC-BY /
  // CC-BY-SA require crediting these — the source card shows them.
  license?: string;
  version_title?: string;
}

export interface FileOut {
  name: string;
  title: string;
  content: string;
}

export interface Message {
  id?: number;
  role: "user" | "assistant";
  text: string;
  intent?: Intent;
  citations: Citation[];
  caveats: string[];
  grounded?: boolean;
  files?: FileOut[];
  created_at?: string;
}

export interface Session {
  id: string;
  first_q: string;
  created_at: string;
  updated_at?: string;
  mode?: Intent | null;
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  grounded: boolean;
  intent: Intent;
  caveats: string[];
  files?: FileOut[];
  session_id?: string;
}

export type Lang = "he" | "en";
