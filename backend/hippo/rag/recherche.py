"""Recherche hybride : mots-clés (BM25) + sens (vecteurs), fusionnés par rang réciproque.

Les deux listes se complètent : BM25 trouve les termes exacts (noms de molécules,
sigles), les vecteurs trouvent les reformulations et les questions en français sur
un corpus en anglais. Si les vecteurs ne sont pas disponibles (pas de clé, pas
d'index, service injoignable), la recherche reste par mots-clés.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

from .bm25 import tokenize
from .embeddings import Embeddeur, VecteursFichier, VecteursPostgres, creer_embeddeur
from .index import CorpusIndex, Hit, load_index

log = logging.getLogger("hippo.rag")
RRF_K = 60  # constante usuelle de la fusion par rang réciproque
CANDIDATS = 30


class MoteurRecherche:
    def __init__(self, index: CorpusIndex | None, embeddeur: Embeddeur | None = None, vecteurs=None) -> None:
        self._index = index
        self.embeddeur = embeddeur
        self.vecteurs = vecteurs

    @property
    def index(self) -> CorpusIndex:
        return self._index if self._index is not None else load_index()

    @property
    def mode(self) -> str:
        return "hybride" if self.embeddeur and self.vecteurs else "mots-clés"

    def chercher(self, query: str, k: int = 5, themes: list[str] | None = None, reuse: list[str] | None = None,
                 per_doc: int = 2) -> list[Hit]:
        idx = self.index
        if self.mode != "hybride":
            return idx.search(query, k=k, themes=themes, reuse=reuse, per_doc=per_doc)
        allowed = idx.filtre(themes, reuse)
        lexical = [i for i, _ in idx.bm25.top(tokenize(query), CANDIDATS, allowed)]
        try:
            q = self.embeddeur.encoder_requete(query)
            semantique = [idx.position(cid) for cid, _ in self.vecteurs.top(q, CANDIDATS, themes, reuse)]
            semantique = [i for i in semantique if i is not None]
        except Exception as exc:  # service d'embeddings indisponible : on garde les mots-clés
            log.warning("recherche par le sens indisponible (%s) : mots-clés seuls", exc)
            return idx.search(query, k=k, themes=themes, reuse=reuse, per_doc=per_doc)
        scores: dict[int, float] = {}
        for liste in (lexical, semantique):
            for rang, i in enumerate(liste):
                scores[i] = scores.get(i, 0.0) + 1.0 / (RRF_K + rang + 1)
        classement = sorted(scores.items(), key=lambda x: -x[1])
        return idx.hits(classement, k=k, per_doc=per_doc)


@lru_cache(maxsize=1)
def moteur_recherche() -> MoteurRecherche:
    try:
        embeddeur = creer_embeddeur()
    except ValueError as exc:
        log.warning("embeddings désactivés : %s", exc)
        embeddeur = None
    vecteurs = None
    if embeddeur is not None:
        url = os.environ.get("DATABASE_URL")
        try:
            if url:
                v = VecteursPostgres(url, embeddeur.modele)
                vecteurs = v if v.nombre() else None
            if vecteurs is None:
                v = VecteursFichier.charger()
                vecteurs = v if v is not None and v.modele == embeddeur.modele else None
        except Exception as exc:
            log.warning("vecteurs indisponibles (%s) : recherche par mots-clés", exc)
            vecteurs = None
    return MoteurRecherche(None, embeddeur, vecteurs)
