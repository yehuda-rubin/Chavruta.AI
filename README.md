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

```
question (he / en)
   │
   ▼  ① Query        detect named commentators, build search vector (bge-m3)
   ▼  ② Retrieval    Qdrant semantic search: anchor pasuk + relevant commentaries
   │                 (+ optional live Sefaria enrichment for extra commentators)
   ▼  ③ Ranking      pasuk-anchored, per-commentator, dedup + similarity sort
   ▼  ④ Generation   grounded answer — local (Ollama) or Nebius (serverless)
   ▼  ⑤ Cite         answer in the question's language + source citations
```

**Two deployment profiles — same code, chosen by env:**

| component  | 💻 Local / offline            | ☁️ Nebius (cloud / scale)              |
|------------|-------------------------------|-----------------------------------------|
| embedding  | `bge-m3` on CPU (query only)   | `bge-m3` GPU job (bulk index)           |
| vector DB  | Qdrant **embedded**            | Qdrant **server** (Docker)              |
| LLM        | `granite4.1:3b` via Ollama     | Token Factory (OpenAI-compatible API)   |
| sources    | pre-downloaded corpus          | + live Sefaria Linker/Links API         |

`VECTOR_BACKEND`, `QDRANT_URL`/`QDRANT_PATH`, `LLM_BACKEND` select the profile.

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

# 3. Load vectors into Qdrant  (CPU, no re-embedding)
docker run -p 6333:6333 -v "%cd%/qdrant_storage:/qdrant/storage" qdrant/qdrant
python scripts/load_to_qdrant.py --in out/ --url http://localhost:6333

# 4. Ask  (retrieval = CPU; generation = Ollama or Nebius)
python scripts/ask.py "What does Rashi say about the creation of light?"
python scripts/ask.py "מה אומר רד\"ק על ספר יונה?" --enrich
streamlit run app.py
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
scripts/
  fetch_corpus.py        fetch all Tanakh + commentators from Sefaria
  embed_corpus_gpu.py    GPU embedding → portable vectors (store-agnostic)
  load_to_qdrant.py      load vectors into Qdrant (embedded or server)
  ask.py                 one-shot RAG CLI
  upload_dataset_hf.py   publish corpus to Hugging Face Hub
src/
  rag_pipeline.py        retrieval + prompt + generation (the chavruta)
  vector_store.py        deployment-agnostic Qdrant layer
  sefaria_client.py      live Sefaria fetcher (verse + commentaries)
  llm_backend.py         Ollama (local) / Nebius (cloud) generation
notebooks/
  embed_corpus_full_kaggle.ipynb   GPU embedding on Kaggle
docs/  PLAN.md · DECISIONS.md · CORPUS.md
```

---

## Status

Torah MVP (bge-m3 + Qdrant + grounded generation) is **working and validated**, including
cross-lingual retrieval. The **full-Tanakh corpus is fetched** (126k chunks) and retrieval is
upgraded to 12 commentators; the full-corpus GPU embedding is the active step.

---

## Documentation

- [docs/PLAN.md](docs/PLAN.md) — master plan & roadmap
- [docs/DECISIONS.md](docs/DECISIONS.md) — technical decisions (ADR) with rationale
- [docs/CORPUS.md](docs/CORPUS.md) — corpus scope & commentators

## Credits

Texts from **[Sefaria](https://www.sefaria.org)** (open, free API). Embeddings: BAAI bge-m3.
Inspired by Sefaria's [Virtual Havruta](https://github.com/Sefaria/AppliedAI). MIT-licensed code.
