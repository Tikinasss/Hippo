"""Recherche hybride : mots-clés (BM25) + sens (vecteurs), fusionnés par rang réciproque.

Les deux listes se complètent : BM25 trouve les termes exacts (noms de molécules,
sigles), les vecteurs trouvent les reformulations et les questions en français sur
un corpus en anglais. Si les vecteurs ne sont pas disponibles (pas de clé, pas
d'index, service injoignable), la recherche reste par mots-clés.
"""
from __future__ import annotations

import logging
import os
import time

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


_RAFRAICHIR_S = 300  # les vecteurs calculés en arrière-plan sont pris en compte sans redémarrer
_cache: dict = {}
_connexions: dict = {}


def moteur_recherche() -> MoteurRecherche:
    now = time.monotonic()
    if "moteur" not in _cache or now - _cache["date"] > _RAFRAICHIR_S:
        _cache.update(moteur=_construire(), date=now)
    return _cache["moteur"]


moteur_recherche.cache_clear = _cache.clear  # même interface qu'un lru_cache (tests, reconstruction d'index)


def _construire() -> MoteurRecherche:
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
                cle = (url, embeddeur.modele)
                if cle not in _connexions:  # un seul pool de connexions, réutilisé à chaque rafraîchissement
                    _connexions[cle] = VecteursPostgres(url, embeddeur.modele)
                v = _connexions[cle]
                vecteurs = v if v.nombre() else None
            if vecteurs is None:
                v = VecteursFichier.charger()
                vecteurs = v if v is not None and v.modele == embeddeur.modele else None
        except Exception as exc:
            log.warning("vecteurs indisponibles (%s) : recherche par mots-clés", exc)
            vecteurs = None
    return MoteurRecherche(None, embeddeur, vecteurs)
