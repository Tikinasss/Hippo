"""CLI du RAG.

    python -m hippo.rag build      # extraire, découper, indexer (mots-clés)
    python -m hippo.rag embed      # calculer les vecteurs (fichier + pgvector si DATABASE_URL)
    python -m hippo.rag search "TIVA versus sevoflurane carbon footprint" -k 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .embeddings import creer_embeddeur, indexer_vecteurs
from .index import build_index, load_index
from .recherche import moteur_recherche


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m hippo.rag")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="extraire, découper et indexer le corpus")
    b.add_argument("--embed", action="store_true", help="calculer aussi les vecteurs")
    sub.add_parser("embed", help="calculer les vecteurs des passages (recherche par le sens)")
    s = sub.add_parser("search", help="chercher dans le corpus")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--theme", action="append")
    s.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.cmd == "build":
        stats = build_index()
        print(f"{stats['documents']} documents, {stats['chunks']} passages indexés.")
        if stats["skipped"]:
            print("Non indexés (absents ou à télécharger) :", ", ".join(stats["skipped"]))
        if not args.embed:
            return

    if args.cmd in ("build", "embed"):
        embeddeur = creer_embeddeur()
        if embeddeur is None:
            print("Pas de fournisseur d'embeddings (GEMINI_API_KEY ou HIPPO_EMBED_PROVIDER) : "
                  "la recherche restera par mots-clés.")
            sys.exit(0 if args.cmd == "build" else 1)
        stats = indexer_vecteurs(load_index().chunks, embeddeur, url_base=os.environ.get("DATABASE_URL"))
        print(f"{stats['passages']} vecteurs rangés ({stats['calcules']} calculés)"
              + (" — fichier et PostgreSQL." if stats["base"] else " — fichier."))
        return

    moteur = moteur_recherche()
    print(f"Recherche : {moteur.mode}", file=sys.stderr)
    hits = moteur.chercher(args.query, k=args.k, themes=args.theme)
    if args.json:
        json.dump([h.to_dict(400) for h in hits], sys.stdout, ensure_ascii=False, indent=2)
        return
    for h in hits:
        print(f"\n[{h.score:.2f}] {h.citation}  ({h.meta.get('license')})")
        print(f"    {h.title}")
        print(f"    {h.text[:300]}…")


if __name__ == "__main__":
    main()
