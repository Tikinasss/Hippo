"""Construction et interrogation de l'index du corpus."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .. import config
from .bm25 import BM25, tokenize
from .chunking import Chunk, chunk_document
from .documents import load_document


def build_index(
    manifest_path: Path = config.MANIFEST_PATH,
    corpus_dir: Path = config.CORPUS_DIR,
    chunks_path: Path = config.CHUNKS_PATH,
) -> dict:
    """Lit le manifest, extrait et découpe chaque document, écrit chunks.jsonl. Renvoie des statistiques."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks: list[Chunk] = []
    skipped: list[str] = []
    for entry in manifest:
        doc = load_document(entry, corpus_dir)
        if doc is None:
            skipped.append(entry["id"])
            continue
        chunks.extend(chunk_document(doc))
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    with chunks_path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    load_index.cache_clear()
    return {"documents": len({c.doc_id for c in chunks}), "chunks": len(chunks), "skipped": skipped}


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    title: str
    heading: str
    text: str
    page: int | None
    score: float
    meta: dict

    @property
    def citation(self) -> str:
        """Référence courte lisible : « Auteur et al., Revue Année — section »."""
        authors = (self.meta.get("authors") or "").split(",")[0].strip()
        if authors and "," in (self.meta.get("authors") or ""):
            authors += " et al."
        parts = [p for p in (authors, self.meta.get("journal"), self.meta.get("year")) if p]
        ref = ", ".join(str(p) for p in parts) or self.title
        where = f"p. {self.page}" if self.page else self.heading
        return f"{ref} — {where}"

    def to_dict(self, max_chars: int | None = None) -> dict:
        text = self.text if max_chars is None or len(self.text) <= max_chars else self.text[:max_chars] + "…"
        return {
            "id": self.chunk_id,
            "doc_id": self.doc_id,
            "titre": self.title,
            "section": self.heading,
            "page": self.page,
            "citation": self.citation,
            "url": self.meta.get("url") or (f"https://doi.org/{self.meta['doi']}" if self.meta.get("doi") else None),
            "licence": self.meta.get("license"),
            "reutilisation": self.meta.get("reuse"),
            "theme": self.meta.get("theme"),
            "score": round(self.score, 3),
            "extrait": text,
        }


class CorpusIndex:
    def __init__(self, chunks: list[dict]) -> None:
        self.chunks = chunks
        self.bm25 = BM25([tokenize(f"{c['title']} {c['heading']} {c['text']}") for c in chunks])

    @classmethod
    def from_file(cls, path: Path) -> "CorpusIndex":
        if not path.exists():
            raise FileNotFoundError(
                f"Index absent ({path}). Lancez d'abord : python -m hippo.rag build"
            )
        with path.open(encoding="utf-8") as f:
            return cls([json.loads(line) for line in f if line.strip()])

    def search(
        self,
        query: str,
        k: int = 5,
        themes: list[str] | None = None,
        reuse: list[str] | None = None,
        per_doc: int = 2,
    ) -> list[Hit]:
        allowed = None
        if themes or reuse:
            allowed = {
                i
                for i, c in enumerate(self.chunks)
                if (not themes or c["meta"].get("theme") in themes)
                and (not reuse or c["meta"].get("reuse") in reuse)
            }
        hits: list[Hit] = []
        per_doc_count: dict[str, int] = {}
        for i, score in self.bm25.top(tokenize(query), k * 4, allowed):
            c = self.chunks[i]
            if per_doc_count.get(c["doc_id"], 0) >= per_doc:
                continue  # diversité : pas plus de `per_doc` passages du même document
            per_doc_count[c["doc_id"]] = per_doc_count.get(c["doc_id"], 0) + 1
            hits.append(
                Hit(
                    chunk_id=c["id"],
                    doc_id=c["doc_id"],
                    title=c["title"],
                    heading=c["heading"],
                    text=c["text"],
                    page=c.get("page"),
                    score=score,
                    meta=c["meta"],
                )
            )
            if len(hits) == k:
                break
        return hits

    def get_chunk(self, chunk_id: str) -> dict | None:
        return next((c for c in self.chunks if c["id"] == chunk_id), None)


@lru_cache(maxsize=1)
def load_index(path: Path = config.CHUNKS_PATH) -> CorpusIndex:
    return CorpusIndex.from_file(path)
