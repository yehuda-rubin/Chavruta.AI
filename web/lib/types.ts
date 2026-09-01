// Mirrors the FastAPI response shapes (app/api.py). The active static UI is the behavioural
// source of truth; these types match what /query, /sessions, /lessons actually return.

export type Intent = "qa" | "explain" | "compare" | "halacha" | "lesson" | "chavruta" | "parsha" | "dafyomi" | "sourcesheet";

export interface Citation {
  ref: string;
  // Best-effort Hebrew rendering of `ref` for display (empty when none is known). `ref` itself
  // stays the English/transliterated corpus key — it's used to dedupe/group/key citations, so it
  // must not change based on language.
  ref_he?: string;
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
  // The model's own list of the works it leaned on, cut out of `text` by the server and shown
  // beside the sources rather than inside the answer. Present only for the rollout.
  source_note?: string;
  created_at?: string;
}

export interface Session {
  id: string;
  first_q: string;
  created_at: string;
  updated_at?: string;
  mode?: Intent | null;
  title?: string | null;
  pinned_at?: string | null;
  excluded_from_review?: boolean;
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  grounded: boolean;
  intent: Intent;
  caveats: string[];
  files?: FileOut[];
  source_note?: string;
  session_id?: string;
}

export type Lang = "he" | "en";

// A source the user adds (pasted text or an uploaded file), sent with the next query. Matches the
// static UI. NOTE: the backend QueryRequest does not currently consume attachments, so these are
// UI-parity for now — the same behaviour the static UI has today.
export interface Attachment {
  kind: "text" | "file";
  name: string;
  content: string; // pasted text, or a data: URL for a file
  mime?: string;
}

export interface SavedLesson {
  id: string;
  topic: string;
  audience?: string;
  grade_band?: string;
  length?: string;
  lang?: string;
  created_at: string;
  files?: FileOut[];
  citations?: Citation[];
}

export interface SavedSourceSheet {
  id: string;
  title: string;
  raw_content: string;
  parsed_sheet: Array<Record<string, unknown>>;
  files: FileOut[];
  citations: string[];
  created_at: string;
  message_id?: number | null;
}
