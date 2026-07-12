# 🕍 Chavruta.AI — a trustworthy Torah study partner (RAG over the Jewish bookshelf)

**Chavruta.AI** answers questions on the Jewish bookshelf by **retrieving the actual sources** —
the verse or passage, plus the classical commentators (Rashi, Ramban, Ibn Ezra, Tosafot, Rambam,
and many more) — and generating a **grounded, cited** answer. It quotes the source in its original
language and explains it **in the language you asked in** (Hebrew or English). No invented "divrei
Torah": every claim is anchored in a retrieved source, the way a *chavruta* (study partner) learns
straight from the text.

> Built for the **Nebius Serverless AI Builders Challenge**. Runs both **fully offline** on a
> laptop and **serverless on Nebius** — the same code, one config switch.

---

## Why RAG (and not a fine-tuned model)

Sefaria's own [Virtual Havruta](https://github.com/Sefaria/AppliedAI) team reached the same
conclusion: for sacred texts, **retrieval beats memorization**. A model that *memorizes* Torah
hallucinates; a model that *retrieves* it cites chapter and verse. Chavruta.AI puts the knowledge
in a **vector index**, not in the weights. The LLM is the *voice*, not the *memory*.

---

## Architecture

Fully redesigned (Spec Kit feature `001-chavruta-redesign` — see [specs/](specs/001-chavruta-redesign/)):
a deployment-agnostic core of **pluggable backends** selected purely by configuration.

```
question (he / en)
   │
   ▼  ① Route        detect language + intent (qa / explain / compare / lesson),
   │                 named commentators ("רש"י"), explicit refs ("Genesis 1:3")
   ▼  ② Retrieve     hybrid search (bge-m3 dense+sparse, RRF in Qdrant)
   │                 + link expansion: anchor chains → commentaries → supercommentaries,
   │                 and across corpora along the chain of transmission
   ▼  ③ Rank         anchored, per-commentator, dedup, optional rerank
   ▼  ④ Generate     grounded prompt = ONLY retrieved sources → local DictaLM / Nebius
   ▼  ⑤ Enforce      citation gate: every claim maps to a real retrieved chunk;
                     fabricated markers stripped; honest "no source found" path
```

**Two deployment profiles — same code, chosen by `CHAVRUTA_PROFILE`:**

| component  | 💻 `local` (offline)              | ☁️ `cloud` (product / scale)            |
|------------|-----------------------------------|-----------------------------------------|
| embedding  | `bge-m3` on CPU (query only)      | `bge-m3` GPU (bulk index)               |
| vector DB  | Qdrant **embedded** (small sets)  | Qdrant **server** (hybrid, full index)  |
| LLM        | **DictaLM** via Ollama (small, offline) | stronger model via Nebius (OpenAI-compatible) |
| reranker   | off (RAM budget)                  | `bge-reranker-v2-m3`                    |

The serving setup ([scripts/serve.ps1](scripts/serve.ps1)) runs **hybrid** retrieval against a
Qdrant **server** (embedded mode cannot do hybrid at this scale) with generation on Nebius
(`Llama-3.3-70B-Instruct`). Every knob is a `CHAVRUTA_*` env var (see `src/chavruta/config/profile.py`).

---

## Application

The app is a **React + Vite SPA** talking to a **FastAPI** backend, with **SQLite** chat history.

| layer        | what it is                                                                 |
|--------------|----------------------------------------------------------------------------|
| `app/api.py` | FastAPI service — sessions, messages, and the `/sessions/{id}/query` RAG endpoint (uvicorn, port 8080) |
| `app/db.py`  | SQLite persistence — conversations survive restarts; deleting a chat cascades to its messages |
| `app/frontend/` | React SPA — three-column "beit midrash" UI, clickable citations, full **Hebrew (RTL) / English (LTR)** i18n with a language toggle (port 5173) |

Conversation history is stored in `chavruta.db` (path overridable via `CHAVRUTA_DB_PATH`; mounted to
a volume in `docker-compose.yml` so it persists). See [app/frontend/README.md](app/frontend/README.md).

### Modes (the `intent` field)

| intent | what it does |
|--------|--------------|
| `qa` | grounded question → cited answer |
| `explain` | a commentator's take on a source |
| `compare` | contrast two commentators / positions |
| `lesson` | build a full beit-midrash / classroom shiur → 3 downloadable `.doc` files (source sheet · flow · full), age-adapted via the lesson-template library (`chavruta_templates`) |
| `halacha` (`shut`) | a responsa-style pesak walkthrough |
| `chavruta` | Socratic study-partner — brings a source and asks a guiding question, learning *with* the user |

Two cross-cutting behaviours: **agentic retrieval** — the model may reply with a `===NEED_SOURCES===`
block to pull more sources mid-answer when retrieval was thin (`chavruta.llm.agentic`); and a
**citation-faithfulness** guard that flags any verbatim quote not found in the retrieved sources.

---

## Corpus — the whole bookshelf

Fetched from [Sefaria](https://www.sefaria.org) (free, open API + bulk export). Each text is stored
**in Hebrew and English**.

**Validated baseline — all of Tanakh** (24 books × ~12 commentators):

| | chunks |
|---|---|
| Pesukim (all Tanakh, HE+EN) | 23,206 |
| Commentary (Rashi, Ramban, Ibn Ezra, Radak, Sforno, Rashbam, Or HaChaim, Malbim, Metzudat David/Zion, Onkelos, Targum Jonathan) | 103,532 |
| **Total** | **126,738** |

**Expanded to the full Sefaria bookshelf** (all 14 categories — Tanakh, Mishnah, Talmud, Halacha,
Midrash, Responsa/Shut, Kabbalah, Liturgy, and more), fetched via `scripts/fetch_*.py`, embedded in
**Nebius GPU jobs**, and distributed as **per-category Hugging Face index repos** (see
[docs/CORPUS.md](docs/CORPUS.md) and [docs/NEBIUS_HALACHA_JOB.md](docs/NEBIUS_HALACHA_JOB.md)). The
**live served hybrid index** currently holds **~449k points** (Tanakh + Mishnah + Talmud + Responsa);
the Halacha library (~594k segments incl. Shulchan Aruch + Mishnah Berura) is embedded and loaded
incrementally without re-embedding what is already in the store.

Embedded with **`BAAI/bge-m3`** (multilingual, 1024-dim) — a Hebrew query and its English
translation land close in vector space, so you can ask in either language.

### Pre-built indexes on Hugging Face

The embedded vectors + payloads are published per category under
**[🤗 Yehuda-Rubin](https://huggingface.co/Yehuda-Rubin)** as `chavruta-index-<slug>` datasets, so
you can load them into Qdrant without re-embedding (see [docs/CORPUS.md](docs/CORPUS.md) §6):

| | | | |
|---|---|---|---|
| [tanakh](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-tanakh) | [mishnah](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-mishnah) | [gemara](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-gemara) | [shut](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-shut) |
| [halacha](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-halacha) | [midrash](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-midrash) | [kabbalah](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-kabbalah) | [musar](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-musar) |
| [liturgy](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-liturgy) | [jewish_thought](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-jewish_thought) | [chasidut](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-chasidut) | [tosefta](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-tosefta) |
| [reference](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-reference) | [second_temple](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-second_temple) | | |

The LoRA "chavruta style" training set is at
[🤗 Yehuda-Rubin/chavruta-torah-mixed](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-torah-mixed).

---

## Quickstart

```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1     # Windows PowerShell
pip install -r requirements.txt
```

### Ask from the CLI (offline, embedded store)

```powershell
# 1. Fetch a corpus from Sefaria (CPU/network) — e.g. Tanakh
python scripts/fetch_corpus.py

# 2. Embed on a GPU (Colab/Kaggle/Nebius — see notebooks/). bge-m3 over 100k+ chunks
#    is impractical on CPU; the GPU notebook produces the vectors.

# 3. Load vectors into the configured store (CPU, no re-embedding)
python scripts/load_to_store.py --profile local

# 4. Pull a local model (one-time) and ask
ollama pull hf.co/dicta-il/DictaLM-3.0-1.7B-Thinking-GGUF:Q8_0
python scripts/ask.py "What does Rashi say about the creation of light?"
python scripts/ask.py "מה אומר רד\"ק על ספר יונה?"
```

### Run the full app (hybrid retrieval + chat UI)

```powershell
# 1. Start the Qdrant server holding the hybrid index
docker compose --profile server up -d qdrant

# 1b. One-time after loading the collection: keyword payload indexes on ref/anchor_ref
#     (required — without them named-ref anchoring & link expansion time out; see docs/CORPUS.md §7.1)
python scripts\create_payload_indexes.py

# 2. Backend (FastAPI on :8080). Two serving modes:
#    • Cloud LLM (Nebius Llama-3.3-70B, reads NEBIUS_API_KEY from .env):
powershell -ExecutionPolicy Bypass -File scripts\serve.ps1
#    • Bridge mode — NO external API; the model is Claude answering the grounded jobs written to
#      data/llm_bridge/pending/ in-session (CHAVRUTA_LLM_BACKEND=bridge):
powershell -ExecutionPolicy Bypass -File scripts\serve_bridge.ps1

# 3. Frontend (Vite dev server on :5173, separate terminal)
cd app\frontend ; npm install ; npm run dev
#    → open http://localhost:5173/ui/chavruta.html   (toggle HE / EN in the top bar)
```

### The trust gate — run the evaluation harness (Principle V)

```powershell
# corpus-aware gates for the full bookshelf (retrieval@K + honesty):
python scripts/run_eval.py --retrieval-only --dataset eval/halacha_v1.jsonl
python scripts/run_eval.py --retrieval-only --dataset eval/lessons_v1.jsonl
# eval/tanakh_v1.jsonl is the HISTORICAL Tanakh-only baseline (see its header) — not a full-corpus gate
```

---

## How it showcases Nebius Serverless

The full lifecycle maps onto **"run a job, serve a model, pay only for what you use"**:

1. **Embedding job** — embed each corpus category on a Nebius GPU (one-off batches; see
   [docs/NEBIUS_HALACHA_JOB.md](docs/NEBIUS_HALACHA_JOB.md)).
2. **Serving** — generation via Nebius Token Factory (OpenAI-compatible, per-token).
3. *(optional)* **Fine-tuning job** — a LoRA "chavruta style" adapter (see `scripts/train_lora.py`
   and [scripts/TRAIN_README.md](scripts/TRAIN_README.md)).

Everything that isn't a one-off GPU embed runs locally — including fully offline.

---

## Project structure

```
src/chavruta/            the deployment-agnostic core (one package, config-driven)
  config/                Profile — local/cloud selection of every backend
  corpus/                CorpusRegistry · unified chunk schema · ingestion · Links graph
  embedding/             EmbeddingBackend → bge-m3 (dense + sparse)
  store/                 VectorStore → Qdrant (embedded / server)
  retrieval/             HybridRetriever (RRF) · LinkExpander · optional Reranker
  llm/                   LLMBackend → LocalLLM (Ollama/DictaLM) · CloudLLM (Nebius)
  generation/            grounded prompts + the citation-enforcement gate
  pipeline/              ChavrutaPipeline — route → retrieve → generate → cite
  intents/               Router — language, intent, commentators, refs
  eval/                  evaluation harness (retrieval@K, grounding, honesty)
app/
  api.py                 FastAPI service (sessions, messages, RAG query endpoint)
  db.py                  SQLite chat-history persistence (sessions + messages, cascade delete)
  frontend/              React + Vite SPA (HE/EN i18n, clickable citations)
scripts/                 fetch_* · embed_corpus_gpu · load_to_store · ask · run_eval · serve.ps1
eval/tanakh_v1.jsonl     versioned evaluation set (HE/EN)
tests/                   contract · integration · unit (the trust guarantees)
specs/001-chavruta-redesign/   spec · plan · research · data-model · contracts · quickstart
docs/                    CORPUS.md · NEBIUS_HALACHA_JOB.md · screenshots/
```

---

## Status

**Redesigned end to end** via Spec Kit (constitution → spec → plan → tasks → implement).
The `src/chavruta/` core implements the MVP capabilities — grounded Q&A, explain/compare
commentators (incl. supercommentary anchor chains), and structured lesson prep — behind
config-swappable backends, with a test suite and a versioned evaluation harness. The corpus has
grown from the validated Tanakh baseline (126k chunks) to the full Sefaria bookshelf, embedded on
Nebius and served from a ~449k-point hybrid Qdrant index. The React SPA + FastAPI app ships with
persistent SQLite chat history and full Hebrew/English UI. Halachic *rulings* remain advisory only,
never a substitute for a competent rav (Constitution Principle VIII).

---

## Documentation

- [specs/001-chavruta-redesign/](specs/001-chavruta-redesign/) — spec · plan · research · data-model · contracts · quickstart
- [docs/CORPUS.md](docs/CORPUS.md) — corpus scope & commentators
- [docs/NEBIUS_HALACHA_JOB.md](docs/NEBIUS_HALACHA_JOB.md) — Nebius embedding-job guide (no Docker) + screenshots
- [.specify/memory/constitution.md](.specify/memory/constitution.md) — the project constitution (governing principles)

## Credits

Texts from **[Sefaria](https://www.sefaria.org)** (open, free API). Embeddings: BAAI bge-m3.
Inspired by Sefaria's [Virtual Havruta](https://github.com/Sefaria/AppliedAI). MIT-licensed code.
