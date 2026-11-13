"""Découpage des sections en passages (chunks) citables."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .documents import Document

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9(])")


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    heading: str
    text: str
    page: int | None
    meta: dict

    def to_dict(self) -> dict:
        return asdict(self)


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    """Coupe un texte trop long en morceaux, de préférence en fin de phrase, avec recouvrement."""
    if len(text) <= max_chars:
        return [text]
    sentences = _SENTENCE_END.split(text)
    pieces: list[str] = []
    current = ""
    for sent in sentences:
        while len(sent) > max_chars:  # phrase géante (tableau aplati, liste)
            head, sent = sent[:max_chars], sent[max_chars - overlap :]
            if current:
                pieces.append(current)
                current = ""
            pieces.append(head)
        if len(current) + len(sent) + 1 > max_chars and current:
            pieces.append(current)
            tail = current[-overlap:] if overlap else ""
            # recommence sur une frontière de mot
            tail = tail[tail.find(" ") + 1 :] if " " in tail else tail
            current = f"{tail} {sent}".strip()
        else:
            current = f"{current} {sent}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_document(doc: Document, max_chars: int = 1500, overlap: int = 200, min_chars: int = 80) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in doc.sections:
        for piece in _split_long(section.text, max_chars, overlap):
            if len(piece) < min_chars:
                continue
            chunks.append(
                Chunk(
                    id=f"{doc.id}#{len(chunks)}",
                    doc_id=doc.id,
                    title=doc.title,
                    heading=section.heading,
                    text=piece,
                    page=section.page,
                    meta=doc.meta,
                )
            )
    return chunks
