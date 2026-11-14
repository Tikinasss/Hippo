# Hippo

Assistant IA d'écoconception des parcours de soins — prototype pour le hackathon AI for Health.

Hippo aide une équipe soignante à réduire l'empreinte carbone d'un parcours de soins **sans dégrader la qualité ni la sécurité**. Le prototype couvre un seul parcours : la **cure de hernie inguinale en ambulatoire**.

> Principe directeur : l'IA propose, l'équipe soignante décide.

Liste de contrôle du lancement et des données à réunir : [MISE_EN_ROUTE.md](MISE_EN_ROUTE.md).

## Architecture

| Brique | Rôle | Dossier |
| --- | --- | --- |
| Corpus | Documents sources (articles en accès ouvert, recommandations) et leur manifest | `corpus/` |
| RAG | Extraction, découpage, recherche hybride (mots-clés BM25 + sens par embeddings) avec citation | `backend/hippo/rag/` |
| Données | Facteurs d'émission, parcours, fiches d'alternatives (JSON sourcés) | `backend/hippo/data/` |
| Moteur de calcul | Impact par étape en fourchette, déterministe, testé — aucun chiffre ne vient du LLM | `backend/hippo/engine/` |
| Assistant | LLM avec appel d'outils : calcul, alternatives, sources, fiche action | `backend/hippo/assistant/` |
| Stockage | Équipes, décisions et valeurs locales (journaux datés et signés), conversations : PostgreSQL + pgvector, ou fichier JSON sans Docker | `backend/hippo/store/` |
| API | FastAPI, relie interface, moteur, stockage et assistant | `backend/hippo/api/` |
| Interface | Next.js, écrans issus des maquettes | `frontend/` |

## Démarrage avec Docker (recommandé)

Prérequis : Docker Desktop. Une seule commande lance la base PostgreSQL (avec pgvector), l'API et l'interface.

```bash
cp backend/.env.example backend/.env    # puis y mettre la clé du modèle (voir plus bas)
docker compose up --build
```

- Interface : http://localhost:3000 (démo : http://localhost:3000/?equipe=demo)
- API et documentation : http://localhost:8000/docs
- État du service (stockage, recherche, modèle) : http://localhost:8000/api/sante

Au premier démarrage, l'API applique les migrations, télécharge le corpus ouvert s'il manque, construit l'index et calcule les vecteurs si une clé Gemini est présente. Le corpus et l'index restent dans `corpus/` sur le poste ; les données d'équipe sont dans le volume Docker `hippo-db`.

Arrêter : `docker compose down` (les données restent). Tout effacer, base comprise : `docker compose down -v`.

## Démarrage sans Docker (développement)

```bash
# 1. Corpus : télécharge les articles en accès ouvert (4 PDF sont à ajouter à la main, voir corpus/manifest.json)
python -I corpus/fetch_corpus.py

# 2. Backend
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Linux/macOS : .venv/bin/python
.venv/Scripts/python -m hippo.rag build              # index par mots-clés
.venv/Scripts/python -m hippo.rag embed              # vecteurs (facultatif, demande GEMINI_API_KEY)
.venv/Scripts/python -m pytest                        # tests

# 3. API
.venv/Scripts/python -m uvicorn hippo.api.main:app --reload --port 8000
```

Sans `DATABASE_URL`, les décisions et les valeurs locales sont enregistrées dans `backend/var/hippo.json`. Pour utiliser la base du conteneur avec une API lancée à la main : `docker compose up -d db`, puis `DATABASE_URL=postgresql://hippo:hippo@127.0.0.1:5433/hippo` dans `backend/.env`.

```bash
# 4. Interface (dans un autre terminal ; relaie /api vers le backend, réglable avec HIPPO_API_URL)
cd frontend
npm install
npm run dev        # http://localhost:3000
```

Tests de la base PostgreSQL : `HIPPO_TEST_DATABASE_URL=postgresql://hippo:hippo@127.0.0.1:5433/hippo python -m pytest tests/test_store.py`.

## Équipes, décisions et données locales

- **Équipe** : un établissement et un service (`?equipe=chu-lyon` dans l'URL). L'équipe `demo` est créée automatiquement ; d'autres se créent avec `POST /api/equipes`.
- **Décisions** : retenir une option ou la mettre en discussion est enregistré au nom de la personne (champ « Vous êtes » en haut de l'écran) et partagé par toute l'équipe. L'historique complet est dans l'onglet Plan d'action.
- **Données locales** : l'onglet du même nom remplace une hypothèse (distance, énergie du bloc…) par la valeur réelle du service, avec son origine. Le calcul, la part d'hypothèses et la fiche HAS en tiennent compte aussitôt. On peut revenir à l'hypothèse ; l'historique reste.
- **Conversations** de l'assistant : enregistrées, elles survivent à un redémarrage de l'API.

### Modèle de l'assistant

L'assistant fonctionne avec Claude ou avec toute API compatible OpenAI. Il suffit de définir **une** clé : le fournisseur est détecté automatiquement (dans cet ordre). Les outils, les citations et les garde-fous sont les mêmes partout ; seule la qualité des réponses varie selon le modèle.

| Fournisseur | Variable à définir | Modèle par défaut (`HIPPO_MODEL` pour changer) |
| --- | --- | --- |
| Claude (Anthropic) | `ANTHROPIC_API_KEY` | `claude-opus-5-5` |
| OpenRouter | `OPENROUTER_API_KEY` + `HIPPO_MODEL` (obligatoire, un modèle qui gère les outils) | — |
| Mistral | `MISTRAL_API_KEY` | `mistral-large-latest` |
| Gemini | `GEMINI_API_KEY` | `gemini-3.8-flash` |
| Ollama (local, sans clé) | `HIPPO_LLM_PROVIDER=ollama` | `llama3.1:8b` |
| Autre API compatible OpenAI | `HIPPO_LLM_PROVIDER=openai_compatible`, `HIPPO_LLM_BASE_URL`, `HIPPO_LLM_API_KEY`, `HIPPO_MODEL` | — |

Le plus simple : copier `backend/.env.example` en `backend/.env` et y mettre la clé, par exemple `GEMINI_API_KEY=...`. Ce fichier est lu au démarrage de l'API et n'est jamais commité. Une variable d'environnement déjà définie garde la priorité sur le fichier.

http://localhost:8000/api/sante indique le fournisseur et le modèle utilisés.

| Autre variable | Rôle | Défaut |
| --- | --- | --- |
| `HIPPO_LLM_PROVIDER` | Forcer un fournisseur | détecté |
| `HIPPO_EFFORT` | Effort de réflexion, Claude uniquement (`low`, `medium`, `high`) | `medium` |
| `HIPPO_CORS_ORIGINS` | Origines autorisées pour l'interface | `http://localhost:3000` |
| `DATABASE_URL` | Base PostgreSQL (fournie par Docker Compose) | fichier `backend/var/hippo.json` |
| `HIPPO_EMBED_PROVIDER` | Embeddings pour la recherche par le sens (`gemini`, `ollama`, `openai_compatible`, `aucun`) | `gemini` si `GEMINI_API_KEY`, sinon `aucun` |
| `HIPPO_EQUIPE_ETABLISSEMENT`, `HIPPO_EQUIPE_SERVICE` | Nom de l'équipe par défaut | CHU de démonstration, Chirurgie ambulatoire |

## Principes de conception

- **Pas de chiffre inventé.** Les impacts viennent du moteur de calcul. Le garde-fou de l'assistant refuse toute valeur en CO₂e ou en % absente des résultats d'outils.
- **Pas de suggestion sans source.** Chaque alternative cite au moins une source ; l'assistant cite avec `[S:id]`, contrôlé puis numéroté. Une réponse non sourcée est corrigée une fois, puis bloquée.
- **Des fourchettes, pas des chiffres au kilo près.** Trois scénarios cohérents (bas, central, haut). Les hypothèses non sourcées sont marquées et leur poids dans le total est affiché.
- **Deux statuts.** « Validée » (recommandation professionnelle) ou « à discuter en équipe » (preuve partielle, choix d'organisation).
- **Tout est tracé.** Décisions et valeurs locales sont des journaux en ajout seul : qui, quoi, quand, d'où vient le chiffre.
- **Aucune donnée patient.**
