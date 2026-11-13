"""Chemins et réglages partagés."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

CORPUS_DIR = Path(os.environ.get("HIPPO_CORPUS_DIR", REPO_ROOT / "corpus"))
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
INDEX_DIR = Path(os.environ.get("HIPPO_INDEX_DIR", CORPUS_DIR / "index"))
CHUNKS_PATH = INDEX_DIR / "chunks.jsonl"

DATA_DIR = Path(__file__).resolve().parent / "data"
