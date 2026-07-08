# Quickstart & Validation: Chavruta.AI (offline profile)

Proves the redesigned system works end to end on the **offline profile** (CPU-only laptop)
and that the trust gate runs. Commands are Windows PowerShell (the project's shell).

## Prerequisites

- Python 3.13 venv at `.venv` (exists).
- Ollama installed, with the local model pulled (DictaLM-2.0 Q4, ~4.4GB):
  `ollama pull dictalm2.0-instruct:q4_k_m`  *(model id is config-driven; swap if RAM-tight)*
- The Tanakh corpus already fetched (`data/processed/…`) and embedded vectors available.
- Profile set to local (default): `$env:CHAVRUTA_PROFILE = "local"`.

## Setup (one-time, offline-capable)

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Load the embedded corpus vectors into the local (embedded) Qdrant store:
python scripts/load_to_store.py --profile local
```

## Validation scenarios

References: data model → [data-model.md](./data-model.md); behavior →
[contracts/pipeline-query.md](./contracts/pipeline-query.md).

### 1. Grounded Q&A (User Story 1 — P1)
```powershell
python scripts/ask.py "What does Rashi say about the creation of light?"
```
**Expected**: an answer grounded in Rashi's actual comment, with a clickable citation that
resolves to that source. No claim without a citation.

### 2. Bilingual parity (FR-010/011)
```powershell
python scripts/ask.py "מה אומר רד״ק על ספר יונה?"
```
**Expected**: a Hebrew answer quoting the Hebrew source, citing it; the English form of the
same question retrieves the same underlying source.

### 3. Honest no-source (FR-003 / SC-002)
```powershell
# Ask about any work that is NOT loaded in your current store (adjust to your corpus).
python scripts/ask.py "What does the Zohar say about the sefirot of creation?"
```
**Expected**: an honest "no grounded source found in the current corpus" response for a work
outside the loaded corpus — **no fabricated** answer or citation. (Originally validated when
only the Tanakh MVP was loaded; pick a work you have not ingested yet.)

### 4. Explain & compare commentators (User Story 2 — P2)
```powershell
python scripts/ask.py "How do Rashi and Ibn Ezra differ on Genesis 1:1?"
```
**Expected**: both positions, each attributed correctly, with the disagreement surfaced and
each cited.

### 5. Lesson preparation (User Story 3 — P3)
```powershell
python scripts/ask.py --intent lesson "Prepare a lesson on teshuva in the book of Jonah"
```
**Expected**: a structured outline (sources, flow, discussion points) where every cited
source resolves.

### 6. Chat UI (in-session context, Principle VII)
```powershell
# Backend (FastAPI on :8080) — for hybrid retrieval, start Qdrant server first:
#   docker compose --profile server up -d qdrant
powershell -ExecutionPolicy Bypass -File scripts\serve.ps1
# Frontend (Vite on :5173, separate terminal):
cd app\frontend ; npm install ; npm run dev   # → http://localhost:5173
```
**Expected**: ask a question, get a cited answer with clickable citations rendered RTL/LTR
correctly; a follow-up question uses the conversation's context (persisted in SQLite); the
HE/EN toggle switches the whole UI and the answer language; responsive feedback.

### 7. Trust gate — evaluation harness (Principle V / SC-001/002/008)
```powershell
python scripts/run_eval.py --profile local --dataset eval/tanakh_v1.jsonl
```
**Expected**: a reproducible report with retrieval@K and grounding scores over the 100+
question set; the score is comparable across runs so regressions are detectable.

## Profile-parity check (Principle II / SC-006)
```powershell
$env:CHAVRUTA_PROFILE = "cloud"   # requires Nebius + Qdrant server config
python scripts/run_eval.py --profile cloud --dataset eval/tanakh_v1.jsonl
```
**Expected**: same code path; citations resolve to the same sources as the local run
(quality/latency may differ, behavior does not).

## Done when
- Scenarios 1–6 behave as described; scenario 3 never fabricates.
- The eval harness (7) runs and reports comparable scores.
- The same dataset runs under both profiles with config-only changes.
