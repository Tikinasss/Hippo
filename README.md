# Hippo

Assistant IA d'écoconception des parcours de soins — prototype pour le hackathon AI for Health.

Hippo aide une équipe soignante à réduire l'empreinte carbone d'un parcours de soins **sans dégrader la qualité ni la sécurité**. Le prototype couvre un seul parcours : la **cure de hernie inguinale en ambulatoire**.

> Principe directeur : l'IA propose, l'équipe soignante décide.

## Architecture

| Brique | Rôle | Dossier |
| --- | --- | --- |
| Corpus | Documents sources (articles en accès ouvert, recommandations) et leur manifest | `corpus/` |
| RAG | Extraction, découpage et recherche avec citation dans le corpus | `backend/hippo/rag/` |
| Données | Facteurs d'émission, parcours, fiches d'alternatives (JSON sourcés) | `backend/hippo/data/` |
| Moteur de calcul | Impact par étape en fourchette, déterministe, testé — aucun chiffre ne vient du LLM | `backend/hippo/engine/` |
| Assistant | LLM avec appel d'outils : calcul, alternatives, sources, fiche action | `backend/hippo/assistant/` |
| API | FastAPI, relie interface, moteur et assistant | `backend/hippo/api/` |
| Interface | Next.js, écrans issus des maquettes | `frontend/` |

## Démarrage rapide

```bash
# 1. Corpus (télécharge les articles en accès ouvert)
python -I corpus/fetch_corpus.py
```

Les étapes suivantes sont documentées au fil des features.
