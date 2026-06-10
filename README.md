# 🕍 Chavruta.AI — a trustworthy Torah study partner (RAG over Sefaria)

**Chavruta.AI** answers questions on Tanakh by **retrieving the actual sources** — the verse,
plus classical commentators (Rashi, Ramban, Ibn Ezra, Radak, Sforno, Malbim, and more) — and
generating a **grounded, cited** answer. It quotes the Hebrew source and explains it **in the
language you asked in** (Hebrew or English). No invented "divrei Torah": every claim is anchored
in a retrieved source, the way a *chavruta* (study partner) learns straight from the text.

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
   ▼  ③ Rank         pasuk-anchored, per-commentator, dedup, optional rerank
   ▼  ④ Generate     grounded prompt = ONLY retrieved sources → local DictaLM / Nebius
   ▼  ⑤ Enforce      citation gate: every claim maps to a real retrieved chunk;
                     fabricated markers stripped; honest "no source found" path
```

**Two deployment profiles — same code, chosen by `CHAVRUTA_PROFILE`:**

| component  | 💻 `local` (offline)              | ☁️ `cloud` (product / scale)            |
|------------|-----------------------------------|-----------------------------------------|
| embedding  | `bge-m3` on CPU (query only)      | `bge-m3` GPU (bulk index)               |
| vector DB  | Qdrant **embedded**               | Qdrant **server**                       |
| LLM        | **DictaLM-3.0 1.7B Q8** via Ollama (~1.8GB) | stronger model via Nebius (OpenAI-compatible) |
| reranker   | off (RAM budget)                  | `bge-reranker-v2-m3`                    |

Every knob is a `CHAVRUTA_*` env var (see `src/chavruta/config/profile.py`).

---

## Corpus — all of Tanakh

Fetched from [Sefaria](https://www.sefaria.org) (free, open): **24 books × ~12 commentators**.

| | chunks |
|---|---|
| Pesukim (all Tanakh, HE+EN) | 23,206 |
| Commentary (Rashi, Ramban, Ibn Ezra, Radak, Sforno, Rashbam, Or HaChaim, Malbim, Metzudat David/Zion, Onkelos, Targum Jonathan) | 103,532 |
| **Total** | **126,738** |

Embedded with **`BAAI/bge-m3`** (multilingual, 1024-dim) — a Hebrew query and its English
translation land close in vector space, so you can ask in either language. See [docs/CORPUS.md](docs/CORPUS.md).

---

## Quickstart

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt

# 1. Fetch the corpus from Sefaria  (CPU/network)
python scripts/fetch_corpus.py                     # → data/processed/all_chunks_full.json

# 2. Embed on a GPU  (Colab/Kaggle/Nebius — see notebooks/)
#    bge-m3 over 126k chunks is impractical on CPU; run the GPU notebook → corpus_vectors.npy

# 3. Load vectors into the configured store  (CPU, no re-embedding)
python scripts/load_to_store.py --in out/ --profile local    # embedded Qdrant, offline

# 4. Pull the local model (one-time, ~1.8GB) and ask
ollama pull hf.co/dicta-il/DictaLM-3.0-1.7B-Thinking-GGUF:Q8_0
python scripts/ask.py "What does Rashi say about the creation of light?"
python scripts/ask.py "מה אומר רד\"ק על ספר יונה?"
streamlit run app/streamlit_app.py

# 5. The trust gate — run the evaluation harness (Principle V)
python scripts/run_eval.py --dataset eval/tanakh_v1.jsonl --retrieval-only
```

---

## How it showcases Nebius Serverless

The full lifecycle maps onto **"run a job, serve a model, pay only for what you use"**:

1. **Embedding job** — embed the 126k-chunk corpus on a Nebius GPU (one-off batch).
2. **Serving** — generation via Nebius Token Factory (OpenAI-compatible, per-token).
3. *(optional)* **Fine-tuning job** — a LoRA "chavruta style" adapter (see `scripts/train_lora.py`).

Everything that isn't the one-off GPU embed runs locally — including fully offline.

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
app/streamlit_app.py     RTL-aware chat UI with clickable citations
scripts/                 fetch_corpus · embed_corpus_gpu · load_to_store · ask · run_eval
eval/tanakh_v1.jsonl     versioned 120-question evaluation set (HE/EN)
tests/                   contract · integration · unit (the trust guarantees)
specs/001-chavruta-redesign/   spec · plan · research · data-model · contracts
docs/  PLAN.md · DECISIONS.md · CORPUS.md
```

---

## Status

**Redesigned end to end** via Spec Kit (constitution → spec → plan → tasks → implement).
The new `src/chavruta/` core implements all three MVP capabilities — grounded Q&A,
explain/compare commentators (incl. supercommentary anchor chains), and structured lesson
prep — behind config-swappable backends, with a 41-test suite and a 120-question evaluation
harness. The full-Tanakh corpus (126k chunks) is fetched and embedded; remaining: load it
into the embedded store on the target machine and run the live eval gate (see
[specs/001-chavruta-redesign/quickstart.md](specs/001-chavruta-redesign/quickstart.md)).
Halachic guidance is deferred until a halachic corpus is added (Constitution Principle VIII).

---

## Documentation

- [docs/PLAN.md](docs/PLAN.md) — master plan & roadmap
- [docs/DECISIONS.md](docs/DECISIONS.md) — technical decisions (ADR) with rationale
- [docs/CORPUS.md](docs/CORPUS.md) — corpus scope & commentators

## Credits

Texts from **[Sefaria](https://www.sefaria.org)** (open, free API). Embeddings: BAAI bge-m3.
Inspired by Sefaria's [Virtual Havruta](https://github.com/Sefaria/AppliedAI). MIT-licensed code.
