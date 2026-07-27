# Third-party content — the texts are not covered by the code licence

Chavruta.AI is MIT-licensed **software** (see [LICENSE](LICENSE)). It is not a licence to the
Jewish texts it retrieves. Those come from [Sefaria](https://www.sefaria.org) and each one carries
the licence of its own **edition** — Sefaria grants rights per `(title, language, versionTitle)`,
not per work and not per author. Two Hebrew editions of the same tractate can differ.

## What the shipped corpus contains

The production collection (`chavruta_commercial`, ~2.4M chunks across 15 tiers) was built by asking
Sefaria which editions exist for each source and keeping only those that positively grant
commercial reproduction. Verified 2026-07-20:

| licence | sources | obligation when the text is reproduced |
|---|---|---|
| Public Domain | 5,338 | none |
| CC0 | 1,205 | none |
| CC-BY | 464 | attribution |
| CC-BY-SA | 87 | attribution **and** share-alike |
| CC-BY-NC / copyrighted / unknown | **0** | — (excluded) |

Editions with no commercially-usable version were skipped outright, not downgraded — among them the
Steinsaltz commentary, most of the Zohar, and the William Davidson Talmud (CC-BY-NC). The rule is
enforced in code and fails closed: `rights.allows_commercial_use()` returns True only for Public
Domain, CC0, CC-BY and CC-BY-SA, and treats "unknown" as forbidden.

> The older `chavruta` collection and the `Yehuda-Rubin/chavruta-index-*` datasets are the
> **mixed-licence** research corpus. They contain CC-BY-NC and copyrighted editions and must not be
> reproduced to users of a paid product. `scripts/load_all_indexes.py` builds that corpus, and
> targets a separate collection for exactly this reason.

## If you redistribute the texts

Retrieving a source and showing it to a user is reproduction, so the obligations attach:

- **Attribution (CC-BY, CC-BY-SA).** Credit in TASL shape — Title, Author, Source, Licence — not a
  bare "from Sefaria". `rights.attribution_line()` produces it, and generated source sheets carry it.

  **How the licence is known.** The shipped collection carries `license` and `version_title` **empty
  on every point**, so until 2026-07-27 that line rendered blank and this file promised more than the
  code delivered. Licence belongs to the *edition*, not to a chunk, so it is now resolved per work at
  read time from `src/chavruta/corpus/data/licenses.json` — built by `scripts/build_license_table.py`
  from the per-tier records the corpus build itself produced, i.e. **which edition was actually
  ingested**, not which editions Sefaria happens to offer today. A per-chunk backfill was measured at
  ~5 points/sec against the on-disk collection and abandoned as pointless.

  **The limit, stated plainly:** a work missing from that table gets **no credit line**. The table
  holds 5,828 titles and covers the fifteen tiers that were built through that pipeline; anything
  added by another route must be added to it, or it will be reproduced uncredited.
- **Share-alike (CC-BY-SA).** A derivative *of the text* must keep the same licence. Your own code
  is not a derivative of the text.

  **What the generated documents do about it.** Attribution answers "who wrote this passage";
  share-alike answers "what may the person holding this FILE do with it", and that second question
  is the one a teacher downloading a source sheet actually faces. So a sheet containing CC-BY or
  CC-BY-SA material now carries a licence footer (`rights.document_license_notice()`), and the
  CC-BY-SA sources are **named** in it — "some of this is share-alike" tells a reader they have a
  problem without telling them where. The full lesson gets the same footer when share-alike is in
  play, because it is the file most likely to be edited and passed on. A sheet built only from
  Public Domain and CC0 sources gets nothing, which is most of them.

  **The reading this rests on, stated openly because it is the one point here a lawyer should
  check.** A source sheet reproduces passages intact alongside our own material, which under CC 4.0
  makes it a *Collection* rather than *Adapted Material*: share-alike attaches to those passages and
  does not extend to the lesson written around them. Under the stricter reading — that the document
  as a whole is a derivative — every lesson touching one of those 87 sources would have to ship
  under CC-BY-SA, including the teacher's own work. The footer states the obligation on the parts,
  which is true either way; it does not license the whole document away on the strength of the
  stricter reading.

Sefaria's own terms and its API terms of service apply to how the texts are obtained.

## Models and libraries

Embeddings use [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) (MIT). Generation calls an external
API (Nebius Token Factory, serving Qwen3) under that provider's terms; the bridge backend calls no
external LLM. Retrieval uses Qdrant (Apache-2.0). Each dependency keeps its own licence.

---

**Not legal advice.** There is no known precedent for a paid product over a Sefaria-derived corpus.
Before charging money, have a lawyer review this. See `docs/COMMERCIAL_CORPUS.md` for how each
edition was chosen and `src/chavruta/corpus/rights.py` for the enforcement.
