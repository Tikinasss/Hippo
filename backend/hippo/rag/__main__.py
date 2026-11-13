"""CLI du RAG.

    python -m hippo.rag build
    python -m hippo.rag search "TIVA versus sevoflurane carbon footprint" -k 5
"""
from __future__ import annotations

import argparse
import json
import sys

from .index import build_index, load_index


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m hippo.rag")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="extraire, découper et indexer le corpus")
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
        return

    hits = load_index().search(args.query, k=args.k, themes=args.theme)
    if args.json:
        json.dump([h.to_dict(400) for h in hits], sys.stdout, ensure_ascii=False, indent=2)
        return
    for h in hits:
        print(f"\n[{h.score:.2f}] {h.citation}  ({h.meta.get('license')})")
        print(f"    {h.title}")
        print(f"    {h.text[:300]}…")


if __name__ == "__main__":
    main()
