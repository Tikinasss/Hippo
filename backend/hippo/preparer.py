"""Préparation au démarrage : base, corpus, index, vecteurs. Chaque étape est idempotente.

    python -m hippo.preparer             # base, corpus, index (bloquant, avant de lancer l'API)
    python -m hippo.preparer --vecteurs  # vecteurs manquants (long : à lancer en arrière-plan)

1. applique les migrations PostgreSQL (si DATABASE_URL) ;
2. télécharge le corpus ouvert s'il est absent (Europe PMC, PDF publics) ;
3. construit l'index par mots-clés s'il est absent ;
4. (--vecteurs) calcule les vecteurs manquants si un fournisseur d'embeddings est configuré.

Seule une erreur de base de données est bloquante : sans corpus ou sans vecteurs,
l'application démarre quand même (recherche réduite ou par mots-clés). Les vecteurs
calculés en arrière-plan sont pris en compte par l'API dans les cinq minutes.
"""
from __future__ import annotations

import os
import subprocess
import sys

from . import config


def _etape(titre: str) -> None:
    print(f"[hippo] {titre}", flush=True)


def preparer_base_et_corpus() -> None:
    url = os.environ.get("DATABASE_URL")
    if url:
        from .store.postgres import StockagePostgres

        s = StockagePostgres(url, migrer=False)
        faites = s.migrer()
        s.fermer()
        _etape(f"base PostgreSQL à jour ({', '.join(faites) if faites else 'aucune migration nouvelle'})")

    if config.CHUNKS_PATH.exists():
        return
    raw = config.CORPUS_DIR / "raw"
    script = config.CORPUS_DIR / "fetch_corpus.py"
    if not any(raw.glob("epmc/*.xml")) and script.exists() and os.environ.get("HIPPO_FETCH_CORPUS", "1") == "1":
        _etape("téléchargement du corpus ouvert (Europe PMC, PDF publics)…")
        if subprocess.run([sys.executable, str(script)], cwd=config.CORPUS_DIR).returncode:
            _etape("téléchargement incomplet : l'index sera construit avec ce qui est disponible")
    try:
        from .rag import build_index

        stats = build_index()
        _etape(f"index construit : {stats['documents']} documents, {stats['chunks']} passages")
    except Exception as exc:  # pas de corpus : l'API démarre sans recherche documentaire
        _etape(f"index non construit ({exc})")


def preparer_vecteurs() -> None:
    url = os.environ.get("DATABASE_URL")
    try:
        from .rag import load_index
        from .rag.embeddings import VecteursFichier, VecteursPostgres, creer_embeddeur, indexer_vecteurs

        embeddeur = creer_embeddeur()
        if embeddeur is None:
            _etape("pas de fournisseur d'embeddings : recherche par mots-clés")
            return
        chunks = load_index().chunks
        en_base = VecteursPostgres(url, embeddeur.modele).nombre() if url else None
        fichier = VecteursFichier.charger()
        complet = (fichier is not None and fichier.modele == embeddeur.modele and len(fichier.ids) == len(chunks)
                   and (en_base is None or en_base == len(chunks)))
        if complet:
            _etape(f"vecteurs à jour ({len(chunks)} passages, {embeddeur.modele})")
            return
        _etape("calcul des vecteurs du corpus en arrière-plan…")
        stats = indexer_vecteurs(chunks, embeddeur, url_base=url, journal=_etape)
        _etape(f"{stats['passages']} vecteurs rangés ({stats['calcules']} calculés)")
    except Exception as exc:
        _etape(f"vecteurs incomplets ({type(exc).__name__} : {exc}) ; la recherche utilise ce qui est disponible")


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if "--vecteurs" in args:
        preparer_vecteurs()
    else:
        preparer_base_et_corpus()


if __name__ == "__main__":
    main()
