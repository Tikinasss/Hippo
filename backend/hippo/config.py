"""Chemins et réglages partagés."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

# Clés et réglages locaux (backend/.env, jamais commité). Une variable déjà définie
# dans l'environnement garde la priorité sur le fichier.
load_dotenv(BACKEND_DIR / ".env", override=False)

CORPUS_DIR = Path(os.environ.get("HIPPO_CORPUS_DIR", REPO_ROOT / "corpus"))
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
INDEX_DIR = Path(os.environ.get("HIPPO_INDEX_DIR", CORPUS_DIR / "index"))
CHUNKS_PATH = INDEX_DIR / "chunks.jsonl"

DATA_DIR = Path(__file__).resolve().parent / "data"
