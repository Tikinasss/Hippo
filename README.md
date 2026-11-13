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
# 1. Corpus : télécharge les articles en accès ouvert (4 PDF sont à ajouter à la main, voir corpus/manifest.json)
python -I corpus/fetch_corpus.py

# 2. Backend
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Linux/macOS : .venv/bin/python
.venv/Scripts/python -m hippo.rag build              # index de recherche du corpus
.venv/Scripts/python -m pytest                        # tests

# 3. API (l'assistant a besoin d'une clé : export ANTHROPIC_API_KEY=...)
.venv/Scripts/python -m uvicorn hippo.api.main:app --reload --port 8000
```

Documentation interactive de l'API : http://localhost:8000/docs

```bash
# 4. Interface (dans un autre terminal ; relaie /api vers le backend, réglable avec HIPPO_API_URL)
cd frontend
npm install
npm run dev        # http://localhost:3000
```

Pour la démo, http://localhost:3000/?scenario=demo charge directement les cinq options du scénario de pitch.

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Clé de l'API Claude, pour l'assistant | — |
| `HIPPO_MODEL` | Modèle de l'assistant | `claude-opus-5-5` |
| `HIPPO_EFFORT` | Effort de réflexion (`low`, `medium`, `high`) | `medium` |
| `HIPPO_CORS_ORIGINS` | Origines autorisées pour l'interface | `http://localhost:3000` |

## Principes de conception

- **Pas de chiffre inventé.** Les impacts viennent du moteur de calcul. Le garde-fou de l'assistant refuse toute valeur en CO₂e ou en % absente des résultats d'outils.
- **Pas de suggestion sans source.** Chaque alternative cite au moins une source ; l'assistant cite avec `[S:id]`, contrôlé puis numéroté. Une réponse non sourcée est corrigée une fois, puis bloquée.
- **Des fourchettes, pas des chiffres au kilo près.** Trois scénarios cohérents (bas, central, haut). Les hypothèses non sourcées sont marquées et leur poids dans le total est affiché.
- **Deux statuts.** « Validée » (recommandation professionnelle) ou « à discuter en équipe » (preuve partielle, choix d'organisation).
- **Aucune donnée patient.**
