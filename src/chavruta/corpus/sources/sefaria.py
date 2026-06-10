"""SefariaAdapter — ingest texts + links from the open Sefaria API (research D8/D10).

Used to add a new Work (and its cross-references) as a data/config operation. The existing
Tanakh corpus is already fetched on disk and reused via the processed-chunks loader
(`chavruta.corpus.ingest.load_processed_chunks`); this adapter is the forward path for new
works (Gemara, Halacha, supercommentaries). `requests` is imported lazily.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

from chavruta.corpus.schema import AnchorKind, Chunk, Link, UnitType, Work

API = "https://www.sefaria.org/api"


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


class SefariaAdapter:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _get(self, url: str) -> dict:
        import requests  # lazy

        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def fetch_chunks(self, work: Work, refs: Iterable[str] | None = None) -> Iterator[Chunk]:
        """Yield source Chunks (HE+EN) for the given refs."""
        for ref in (refs or []):
            data = self._get(f"{API}/v3/texts/{ref.replace(' ', '%20')}")
            versions = data.get("versions", [])
            he = en = ""
            for v in versions:
                lang = v.get("language") or v.get("actualLanguage")
                content = v.get("text")
                flat = " ".join(content) if isinstance(content, list) else (content or "")
                if lang == "he" and not he:
                    he = _strip_html(flat)
                elif lang == "en" and not en:
                    en = _strip_html(flat)
            primary = he or en
            if not primary:
                continue
            yield Chunk(
                chunk_id=f"{work.work_id}:{ref}",
                work_id=work.work_id,
                unit_type=UnitType.SOURCE,
                ref=ref,
                lang="he" if he else "en",
                text=primary,
                text_he=he,
                text_en=en,
                deep_link=f"https://www.sefaria.org/{ref.replace(' ', '.')}",
            )

    def fetch_links(self, work: Work, refs: Iterable[str] | None = None) -> Iterator[Link]:
        """Yield cross-reference Links (commentary, quotation, reference) for the refs."""
        for ref in (refs or []):
            for link in self._get(f"{API}/links/{ref.replace(' ', '%20')}"):
                to_ref = link.get("ref") or link.get("anchorRef")
                if not to_ref:
                    continue
                yield Link(
                    from_ref=ref,
                    to_ref=to_ref,
                    from_work_id=work.work_id,
                    to_work_id=_slug(link.get("collectiveTitle", {}).get("en", "") or link.get("category", "")),
                    link_type=link.get("type", "reference"),
                )

    def fetch_commentaries(self, work: Work, refs: Iterable[str]) -> Iterator[Chunk]:
        """Yield commentary Chunks anchored to the given source refs (incl. supercommentary)."""
        for ref in refs:
            for link in self._get(f"{API}/links/{ref.replace(' ', '%20')}"):
                if link.get("category") != "Commentary":
                    continue
                c_ref = link.get("ref")
                commentator = link.get("collectiveTitle", {}).get("en", "") or link.get("index_title", "")
                if not c_ref or not commentator:
                    continue
                he = _strip_html(" ".join(link.get("he", [])) if isinstance(link.get("he"), list) else link.get("he", ""))
                en = _strip_html(" ".join(link.get("text", [])) if isinstance(link.get("text"), list) else link.get("text", ""))
                primary = he or en
                if not primary:
                    continue
                yield Chunk(
                    chunk_id=f"{_slug(commentator)}:{c_ref}",
                    work_id=_slug(commentator),
                    unit_type=UnitType.COMMENTARY,
                    ref=c_ref,
                    lang="he" if he else "en",
                    text=primary,
                    text_he=he,
                    text_en=en,
                    deep_link=f"https://www.sefaria.org/{c_ref.replace(' ', '.')}",
                    anchor_ref=ref,
                    anchor_kind=AnchorKind.SOURCE,
                    commentator_id=_slug(commentator),
                )
