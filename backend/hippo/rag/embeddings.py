"""Vecteurs (embeddings) des passages du corpus, pour la recherche par le sens.

Fournisseur choisi par variables d'environnement :
    HIPPO_EMBED_PROVIDER  gemini | ollama | openai_compatible | aucun
                          (défaut : gemini si GEMINI_API_KEY est défini, sinon aucun)
    HIPPO_EMBED_MODEL     modèle d'embeddings (défaut : gemini-embedding-001 / nomic-embed-text)
    HIPPO_EMBED_BASE_URL, HIPPO_EMBED_API_KEY  pour openai_compatible

Les vecteurs sont rangés dans corpus/index/vecteurs.npz et, si DATABASE_URL est défini,
dans la table `passages` (pgvector). Sans fournisseur, la recherche reste par mots-clés.
"""
from __future__ import annotations

import hashlib
import os
import time
from functools import lru_cache
from pathlib import Path

import numpy as np

from .. import config

DIM = 768  # dimension commune (colonne vector(768) en base)
VECTEURS_PATH = config.INDEX_DIR / "vecteurs.npz"

_PRESETS = {
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "cle": "GEMINI_API_KEY",
               "modele": "gemini-embedding-001", "dimensions": True},
    "ollama": {"base_url": "http://localhost:11434/v1", "cle": None, "modele": "nomic-embed-text", "dimensions": False},
    "openai_compatible": {"base_url": None, "cle": "HIPPO_EMBED_API_KEY", "modele": None, "dimensions": True},
}


class Embeddeur:
    def __init__(self, fournisseur: str, client=None) -> None:
        p = _PRESETS[fournisseur]
        self.fournisseur = fournisseur
        self.modele = os.environ.get("HIPPO_EMBED_MODEL") or p["modele"]
        if not self.modele:
            raise ValueError("HIPPO_EMBED_MODEL est requis pour openai_compatible")
        self._dimensions = p["dimensions"]
        self._client = client
        self._base_url = os.environ.get("HIPPO_EMBED_BASE_URL") or p["base_url"]
        self._cle = os.environ.get("HIPPO_EMBED_API_KEY") or (os.environ.get(p["cle"]) if p["cle"] else "ollama")

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(base_url=self._base_url, api_key=self._cle, timeout=30, max_retries=2)
        return self._client

    def encoder(self, textes: list[str], lot: int = 100, tentatives: int = 6) -> np.ndarray:
        """Vecteurs normalisés (norme 1), forme (n, DIM). Attend et réessaie si le débit est limité."""
        import openai

        sorties = []
        for i in range(0, len(textes), lot):
            morceau = textes[i:i + lot]
            kw = {"dimensions": DIM} if self._dimensions else {}
            for essai in range(tentatives):
                try:
                    r = self.client.embeddings.create(model=self.modele, input=morceau, **kw)
                    break
                except openai.RateLimitError:
                    if essai == tentatives - 1:
                        raise
                    time.sleep(min(60, 5 * 2 ** essai))  # offres gratuites : quelques requêtes par minute
            data = list(r.data)
            if all(getattr(d, "index", None) is not None for d in data):  # Gemini ne renvoie pas toujours l'index
                data.sort(key=lambda d: d.index)
            if len(data) != len(morceau):
                raise ValueError(f"{len(data)} vecteurs reçus pour {len(morceau)} textes")
            sorties.extend(d.embedding for d in data)
        m = np.asarray(sorties, dtype=np.float32)
        if m.ndim != 2 or m.shape[1] != DIM:
            raise ValueError(f"le modèle {self.modele} renvoie des vecteurs de dimension {m.shape[-1]}, il en faut {DIM}")
        return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-12)

    @lru_cache(maxsize=256)
    def encoder_requete(self, texte: str) -> np.ndarray:
        return self.encoder([texte])[0]


def creer_embeddeur() -> Embeddeur | None:
    choix = os.environ.get("HIPPO_EMBED_PROVIDER") or ("gemini" if os.environ.get("GEMINI_API_KEY") else "aucun")
    if choix == "aucun":
        return None
    if choix not in _PRESETS:
        raise ValueError(f"HIPPO_EMBED_PROVIDER inconnu : {choix}")
    return Embeddeur(choix)


def texte_a_encoder(chunk: dict) -> str:
    return f"{chunk['title']}\n{chunk['heading']}\n{chunk['text']}"


def empreinte(chunk: dict, modele: str) -> str:
    return hashlib.sha1(f"{modele}\n{texte_a_encoder(chunk)}".encode("utf-8")).hexdigest()


# --- Rangement des vecteurs ----------------------------------------------------------------


class VecteursFichier:
    """Matrice en mémoire (quelques milliers de passages : un produit matriciel suffit)."""

    def __init__(self, ids: list[str], empreintes: list[str], matrice: np.ndarray, modele: str,
                 meta: dict[str, tuple[str | None, str | None]] | None = None) -> None:
        self.ids, self.empreintes, self.matrice, self.modele = ids, empreintes, matrice, modele
        self.meta = meta or {}  # id -> (thème, réutilisation), pour filtrer

    @classmethod
    def charger(cls, path: Path = VECTEURS_PATH) -> "VecteursFichier | None":
        if not path.exists():
            return None
        d = np.load(path, allow_pickle=False)
        ids = d["ids"].tolist()
        meta = dict(zip(ids, zip(d["themes"].tolist(), d["reuses"].tolist())))
        return cls(ids, d["empreintes"].tolist(), d["matrice"], str(d["modele"]), meta)

    def sauver(self, path: Path = VECTEURS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        themes = [self.meta.get(i, (None, None))[0] or "" for i in self.ids]
        reuses = [self.meta.get(i, (None, None))[1] or "" for i in self.ids]
        np.savez(path, ids=np.array(self.ids), empreintes=np.array(self.empreintes), matrice=self.matrice,
                 modele=np.array(self.modele), themes=np.array(themes), reuses=np.array(reuses))

    def top(self, q: np.ndarray, k: int, themes: list[str] | None = None,
            reuse: list[str] | None = None) -> list[tuple[str, float]]:
        scores = self.matrice @ q
        if themes or reuse:
            masque = np.array([(not themes or self.meta[i][0] in themes) and (not reuse or self.meta[i][1] in reuse)
                               for i in self.ids])
            scores = np.where(masque, scores, -np.inf)
        ordre = np.argsort(-scores)[:k]
        return [(self.ids[j], float(scores[j])) for j in ordre if np.isfinite(scores[j])]


class VecteursPostgres:
    def __init__(self, url: str, modele: str) -> None:
        from pgvector.psycopg import register_vector
        from psycopg_pool import ConnectionPool

        self.modele = modele
        self.pool = ConnectionPool(url, min_size=1, max_size=4, configure=register_vector, open=True)

    def nombre(self) -> int:
        with self.pool.connection() as c:
            return c.execute("SELECT count(*) FROM passages WHERE modele = %s", (self.modele,)).fetchone()[0]

    def top(self, q: np.ndarray, k: int, themes: list[str] | None = None,
            reuse: list[str] | None = None) -> list[tuple[str, float]]:
        sql = "SELECT id, 1 - (embedding <=> %s) FROM passages WHERE modele = %s"
        args: list = [q, self.modele]
        if themes:
            sql += " AND theme = ANY(%s)"
            args.append(themes)
        if reuse:
            sql += " AND reuse = ANY(%s)"
            args.append(reuse)
        sql += " ORDER BY embedding <=> %s LIMIT %s"
        args += [q, k]
        with self.pool.connection() as c:
            return [(r[0], float(r[1])) for r in c.execute(sql, args)]

    def remplacer(self, lignes: list[tuple[str, str, str | None, str | None, str, np.ndarray]]) -> None:
        """Synchronise la table avec l'index : (id, doc_id, thème, réutilisation, empreinte, vecteur)."""
        with self.pool.connection() as c, c.transaction():
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO passages (id, doc_id, theme, reuse, empreinte, modele, embedding) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET doc_id = EXCLUDED.doc_id, "
                    "theme = EXCLUDED.theme, reuse = EXCLUDED.reuse, empreinte = EXCLUDED.empreinte, "
                    "modele = EXCLUDED.modele, embedding = EXCLUDED.embedding",
                    [(i, d, t, r, e, self.modele, v) for i, d, t, r, e, v in lignes])
            c.execute("DELETE FROM passages WHERE NOT (id = ANY(%s))", ([l[0] for l in lignes],))


def indexer_vecteurs(chunks: list[dict], embeddeur: Embeddeur, path: Path = VECTEURS_PATH,
                     url_base: str | None = None, journal=print, lot: int = 100) -> dict:
    """Calcule les vecteurs manquants (les passages inchangés sont réutilisés) et les range.

    Le fichier est réécrit après chaque lot : une interruption (quota, réseau) ne fait
    perdre que le lot en cours, et la commande suivante reprend là où elle s'est arrêtée.
    """
    ancien = VecteursFichier.charger(path)
    connus: dict[str, np.ndarray] = {}
    if ancien and ancien.modele == embeddeur.modele:
        connus = {e: ancien.matrice[j] for j, e in enumerate(ancien.empreintes)}
    empreintes = [empreinte(c, embeddeur.modele) for c in chunks]
    meta = {c["id"]: (c["meta"].get("theme"), c["meta"].get("reuse")) for c in chunks}
    a_faire = [j for j, e in enumerate(empreintes) if e not in connus]
    journal(f"{len(chunks) - len(a_faire)} vecteurs réutilisés, {len(a_faire)} à calculer avec {embeddeur.modele}…")

    def sauver() -> list[int]:
        presents = [j for j, e in enumerate(empreintes) if e in connus]
        matrice = (np.stack([connus[empreintes[j]] for j in presents]).astype(np.float32) if presents
                   else np.zeros((0, DIM), np.float32))
        VecteursFichier([chunks[j]["id"] for j in presents], [empreintes[j] for j in presents], matrice,
                        embeddeur.modele, meta).sauver(path)
        return presents

    for n in range(0, len(a_faire), lot):
        bloc = a_faire[n:n + lot]
        for j, v in zip(bloc, embeddeur.encoder([texte_a_encoder(chunks[j]) for j in bloc], lot=lot)):
            connus[empreintes[j]] = v
        sauver()
        journal(f"  {min(n + lot, len(a_faire))}/{len(a_faire)}")
    presents = sauver()
    stats = {"passages": len(presents), "calcules": len(a_faire), "fichier": str(path), "base": False}
    if url_base:
        VecteursPostgres(url_base, embeddeur.modele).remplacer(
            [(chunks[j]["id"], chunks[j]["doc_id"], meta[chunks[j]["id"]][0], meta[chunks[j]["id"]][1], empreintes[j],
              connus[empreintes[j]]) for j in presents])
        stats["base"] = True
    return stats
