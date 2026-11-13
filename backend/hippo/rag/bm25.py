"""Index BM25 en pur Python : pas de modèle à télécharger, pas de clé d'API.

Le corpus est surtout en anglais : l'assistant reformule la question en anglais
avant d'appeler la recherche (voir l'outil `chercher_sources`). Le tokenizer
retire les accents pour que les requêtes françaises restent utilisables.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?")

STOPWORDS = set(
    """
    a an and are as at be been but by for from has have in into is it its of on or that the their
    there these this to was were which with within without not no than then so such can may also
    le la les un une des du de et en au aux pour par sur dans que qui est sont avec sans ce cette ces
    plus moins son sa ses leur leurs ou ne pas se d l
    """.split()
)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _stem(tok: str) -> str:
    """Racinisation légère (pluriels anglais et français) : suffisant pour BM25."""
    if tok.isdigit() or len(tok) <= 3:
        return tok
    # « therapy », « therapies » et « thérapies » convergent vers « therapie »
    if tok.endswith("ies") and len(tok) > 4:
        return tok[:-1]
    if tok.endswith("y") and len(tok) > 4:
        return tok[:-1] + "ie"
    if tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
        return tok[:-1]
    return tok


def tokenize(text: str) -> list[str]:
    text = strip_accents(text.lower()).replace("₂", "2")
    return [_stem(t) for t in _TOKEN.findall(text) if t not in STOPWORDS]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tfs = [Counter(d) for d in docs]
        self.lens = [len(d) for d in docs]
        self.avgdl = (sum(self.lens) / len(self.lens)) if self.lens else 0.0
        df: Counter[str] = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query: list[str], i: int) -> float:
        tf, dl = self.tfs[i], self.lens[i]
        s = 0.0
        for t in query:
            f = tf.get(t)
            if not f:
                continue
            s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s

    def top(self, query: list[str], k: int, allowed: set[int] | None = None) -> list[tuple[int, float]]:
        q = [t for t in dict.fromkeys(query) if t in self.idf]
        if not q:
            return []
        candidates = range(len(self.tfs)) if allowed is None else allowed
        scored = [(i, self.score(q, i)) for i in candidates]
        scored = [x for x in scored if x[1] > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]
