# 🕍 Chavruta.AI — a trustworthy Torah study partner (RAG over the Jewish bookshelf)

**Chavruta.AI** answers questions on the Jewish bookshelf by **retrieving the actual sources** —
the verse or passage, plus the classical commentators (Rashi, Ramban, Ibn Ezra, Tosafot, Rambam,
and many more) — and generating a **grounded, cited** answer. It quotes the source in its original
language and explains it **in the language you asked in** (Hebrew or English). No invented "divrei
Torah": every claim is anchored in a retrieved source, the way a *chavruta* (study partner) learns
straight from the text.

> Built for the **Nebius Serverless AI Builders Challenge**. Retrieval + embedding run **locally**;
> generation is served by the **Nebius API** (`Qwen3-235B`) — or fully self-contained via the
> **bridge** backend (no external LLM API). One config switch.

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
   ▼  ① Route        language + intent (qa / explain / compare / lesson / halacha / chavruta),
   │                 named commentators ("רש"י"), explicit refs, and INDIRECT refs → landmarks:
   │                 "עשרת הדיברות"→Exodus 20, "פרק שלישי בסנהדרין"→Sanhedrin 45.1 (perek→daf),
   │                 English famous passages ("the binding of Isaac"→Genesis 22)
   ▼  ② Retrieve     hybrid search (bge-m3 dense+sparse, RRF in Qdrant), then:
   │                 • named-ref ANCHORING — fetch the base pasuk/daf + its commentaries. Refs are
   │                   canonicalised to the corpus format ('Genesis.1.1'→'Genesis 1.1', Talmud
   │                   amud→amud-linear) or the anchor silently misses.
   │                 • per-hit relevance floor — prune dense off-topic noise, keep lexical hits
   │                 • base-source floor — reserve slots for base texts (commentary can't crowd out)
   │                 • link expansion: anchor chains → commentaries → supercommentaries
   ▼  ③ Rank         anchored (explicit anchor set), dedup, optional rerank; honest is_empty gate
   ▼  ④ Generate     grounded prompt = ONLY retrieved sources → Nebius API / **bridge** (Claude
   │                 in-session, no external API). Agentic: the model may reply ===NEED_SOURCES===
   │                 to pull more sources mid-answer when retrieval was thin.
   ▼  ⑤ Enforce      citation gate: every claim maps to a real chunk; fabricated markers stripped;
                     verbatim-quote faithfulness check; honest "no source found" path
```

**Two deployment profiles — same code, chosen by `CHAVRUTA_PROFILE`:**

| component  | 💻 `local` (personal machine)     | ☁️ `cloud` (product / scale)            |
|------------|-----------------------------------|-----------------------------------------|
| embedding  | `bge-m3` on CPU (query only)      | `bge-m3` GPU (bulk index)               |
| vector DB  | Qdrant **embedded** (small sets)  | Qdrant **server** (hybrid, full index)  |
| LLM        | Nebius API (`Qwen3-235B`) — or `bridge` (Claude in-session, no API) | Nebius API (`Qwen3-235B`) |
| reranker   | off (RAM budget)                  | `bge-reranker-v2-m3`                    |

Retrieval and embedding run **locally**; generation goes to the **Nebius API** (default) or the
**bridge** backend (Claude answering in-session, no external LLM API). The serving setup
([scripts/serve.ps1](scripts/serve.ps1)) runs **hybrid** retrieval against a Qdrant **server**
(embedded mode cannot do hybrid at this scale) with generation on Nebius
(`Qwen/Qwen3-235B-A22B-Instruct-2507`) — the **default even locally** (`CHAVRUTA_LLM_BACKEND=nebius`,
key from `.env`; `CHAVRUTA_QUERY_PLANNER=heuristic`). The no-API path is
[scripts/serve_bridge.ps1](scripts/serve_bridge.ps1). The local DictaLM/Ollama backend was **removed**.
Every knob is a `CHAVRUTA_*` env var (see `src/chavruta/config/profile.py`).

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

**Expanded to the full Sefaria bookshelf**, fetched via `scripts/fetch_*.py`, embedded on GPU
(Nebius / Kaggle / Lightning), and distributed on **Hugging Face** in two repos:

- 📦 **Source chunks** (raw JSONL per domain — `gemara_chunks.jsonl`, `yerushalmi_chunks.jsonl`, …):
  [`Yehuda-Rubin/chavruta-torah-mixed`](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-torah-mixed)
- 🧠 **Prebuilt indexes** (embedded vectors + sparse + meta, one repo per tier —
  `chavruta-index-yerushalmi`, `chavruta-index-halacha`, …):
  [`Yehuda-Rubin/chavruta-index-*`](https://huggingface.co/Yehuda-Rubin) · load with
  `scripts/bootstrap_rag.py --repo Yehuda-Rubin/chavruta-index-<tier> --append`

See [docs/CORPUS.md](docs/CORPUS.md) and [docs/NEBIUS_HALACHA_JOB.md](docs/NEBIUS_HALACHA_JOB.md). The
**live served hybrid index** now holds **~2.93M points across 15 tiers**: `talmud_bavli` (614k),
`halacha` (594k), `tanakh` (268k), `mishnah` (196k), `midrash`, **`talmud_yerushalmi` (~188k — the
Talmud Yerushalmi + all its meforshim, added 2026-07-13)**, `chasidut`, `jewish_thought`, `responsa`,
`liturgy`, `kabbalah`, `tosefta`, `reference`, `musar`, `second_temple`. New tiers load incrementally
(`bootstrap_rag.py --append`) without re-embedding what is already in the store.

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

### Ask from the CLI (local retrieval + the API)

```powershell
# 1. Fetch a corpus from Sefaria (CPU/network) — e.g. Tanakh
python scripts/fetch_corpus.py

# 2. Embed on a GPU (Colab/Kaggle/Nebius/Lightning — see notebooks/). bge-m3 over 100k+ chunks
#    is impractical on CPU; the GPU notebook produces the vectors.

# 3. Load vectors into the configured store (CPU, no re-embedding)
python scripts/load_to_store.py --profile local

# 4. Ask — retrieval is local; generation goes to the Nebius API (put NEBIUS_API_KEY in .env).
#    For the no-API path set CHAVRUTA_LLM_BACKEND=bridge (Claude answers in-session).
python scripts/ask.py "What does Rashi say about the creation of light?"
python scripts/ask.py "מה אומר רד\"ק על ספר יונה?"
```

### Load the RAG from Hugging Face (first time / fresh machine)

The prebuilt indexes live on Hugging Face (one dataset repo per tier — no re-embedding needed). Pull
them straight into a local Qdrant:

```powershell
docker compose --profile server up -d qdrant          # local Qdrant first

# ALL 15 tiers (~2.93M points) — resumable, skips already-loaded tiers, smallest→largest:
python scripts/load_all_indexes.py                     # add --fresh to drop + reload from scratch

# …or just ONE tier (e.g. the Talmud Yerushalmi):
python scripts/bootstrap_rag.py --repo Yehuda-Rubin/chavruta-index-yerushalmi --out out_yerushalmi --append

python scripts/create_payload_indexes.py               # required once after loading (ref/anchor_ref)
```

Both scripts download the index files (`corpus_vectors.npy` + `corpus_sparse.jsonl` + `corpus_meta.jsonl`)
from `Yehuda-Rubin/chavruta-index-<tier>` and upsert them into the collection. See `docs/CORPUS.md §6`
for the full tier→repo table.

### Run EVERYTHING (full stack)

**Prerequisites:** the corpus/index is already embedded and loaded into the local Qdrant (15 tiers,
~2.93M points — see "Load the RAG" above if not), and `.env` holds `NEBIUS_API_KEY` (write access not
needed for serving). If so, the whole system is just **three commands** — Qdrant → backend → frontend:

```powershell
# 1. Start the Qdrant server holding the hybrid index (data persists on disk between restarts)
docker compose --profile server up -d qdrant

# 1b. One-time after loading the collection: keyword payload indexes on ref/anchor_ref
#     (required — without them named-ref anchoring & link expansion time out; see docs/CORPUS.md §7.1)
python scripts\create_payload_indexes.py

# 2. Backend (FastAPI on :8080). Two serving modes:
#    • DEFAULT — Nebius API (Qwen3-235B-A22B-Instruct), reads NEBIUS_API_KEY from .env. Local infra
#      (CPU embedding + local Qdrant) + generation on the API; CHAVRUTA_QUERY_PLANNER=heuristic:
powershell -ExecutionPolicy Bypass -File scripts\serve.ps1
#    • Bridge mode — NO external API; the model is Claude answering the grounded jobs written to
#      data/llm_bridge/pending/ in-session (CHAVRUTA_LLM_BACKEND=bridge):
powershell -ExecutionPolicy Bypass -File scripts\serve_bridge.ps1

# 3. Frontend (Vite dev server on :5173, separate terminal)
cd app\frontend ; npm install ; npm run dev
#    → open http://localhost:5173/ui/chavruta.html   (toggle HE / EN in the top bar)
```

### Run only a PART of it

**Just one component** — each is independent once its dependency is up, so start only what you need:

```powershell
# • Qdrant only (the data layer — start it, use the CLI/API against it)
docker compose --profile server up -d qdrant           # stop: docker compose stop qdrant

# • Backend only (needs Qdrant up) — the API on :8080, no UI. Good for scripts/curl:
powershell -ExecutionPolicy Bypass -File scripts\serve.ps1

# • Frontend only (needs the backend up) — the static UI proxies /api to :8080:
cd app\frontend ; npm run dev
```

**Load only SOME corpus tiers** (the collection is a set of tiers; each is a separate HF index repo,
loaded incrementally — build a smaller RAG with just the ones you want):

```powershell
# A minimal collection = Tanakh + Bavli only. First load RECREATES; each --append adds on top:
python scripts\bootstrap_rag.py --repo Yehuda-Rubin/chavruta-index-tanakh --out out_tanakh              # no --append ⇒ (re)create
python scripts\bootstrap_rag.py --repo Yehuda-Rubin/chavruta-index-gemara --out out_gemara --append
python scripts\create_payload_indexes.py                                                                # after loading
# add another tier later, on top, WITHOUT touching the rest:
python scripts\bootstrap_rag.py --repo Yehuda-Rubin/chavruta-index-yerushalmi --out out_yerushalmi --append
```

**Switch the generation backend** (a config "part", set before serving):

| backend | how | notes |
|---------|-----|-------|
| Nebius API (default) | `scripts\serve.ps1` | Qwen3-235B; needs `NEBIUS_API_KEY` in `.env` |
| Bridge (no external API) | `scripts\serve_bridge.ps1` | Claude answers `data/llm_bridge/pending/` in-session |

**Stop everything:** Ctrl-C (or kill) the backend + frontend, then `docker compose stop qdrant`.

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

Everything except the one-off GPU embed and the generation call runs locally; generation is the
Nebius API (default) or the in-session bridge (no external LLM API).

---

## Project structure

```
src/chavruta/            the deployment-agnostic core (one package, config-driven)
  config/                Profile — local/cloud selection of every backend
  corpus/                CorpusRegistry · unified chunk schema · ingestion · Links graph
  embedding/             EmbeddingBackend → bge-m3 (dense + sparse)
  store/                 VectorStore → Qdrant (embedded / server)
  retrieval/             HybridRetriever (RRF) · LinkExpander · optional Reranker
  llm/                   LLMBackend → CloudLLM (Nebius API) · BridgeLLM (Claude in-session)
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
grown from the validated Tanakh baseline (126k chunks) to the full Sefaria bookshelf — **~2.93M points
across 15 tiers, incl. the Talmud Yerushalmi** — served from a hybrid Qdrant index with generation on
the Nebius API (Qwen3-235B). The **static offline UI** ([app/frontend/public/ui/chavruta.html](app/frontend/public/ui/chavruta.html);
the React SPA is deprecated) + FastAPI app ship with persistent SQLite chat history and full
Hebrew/English UI. Halachic *rulings* remain advisory only, never a substitute for a competent rav
(Constitution Principle VIII).

---

## Documentation

- [specs/001-chavruta-redesign/](specs/001-chavruta-redesign/) — spec · plan · research · data-model · contracts · quickstart
- [docs/CORPUS.md](docs/CORPUS.md) — corpus scope & commentators
- [docs/NEBIUS_HALACHA_JOB.md](docs/NEBIUS_HALACHA_JOB.md) — Nebius embedding-job guide (no Docker) + screenshots
- [.specify/memory/constitution.md](.specify/memory/constitution.md) — the project constitution (governing principles)

## Credits

Texts from **[Sefaria](https://www.sefaria.org)** (open, free API). Embeddings: BAAI bge-m3.
Inspired by Sefaria's [Virtual Havruta](https://github.com/Sefaria/AppliedAI). MIT-licensed code.
