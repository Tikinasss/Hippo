# Hippo — mise en route et données à réunir

Ce fichier sert de liste de contrôle pour faire vivre le prototype. Une case cochée est faite et vérifiée. Une case vide reste à faire.

État au 14 novembre 2026.

---

## 1. Lancer le prototype sur un poste

### Lancement en une commande (Docker)
- [x] Docker Desktop installé
- [x] `docker-compose.yml` : base PostgreSQL + pgvector, API, interface
- [ ] `docker compose up --build` testé de bout en bout sur ce poste
- [ ] Testé sur un second poste (clone propre du dépôt)

### Prérequis hors Docker
- [x] Python 3.11 ou plus récent
- [x] Node.js 20 ou plus récent
- [x] Dépôt cloné, branche `main` à jour avec GitHub

### Corpus documentaire (RAG)
- [x] 22 articles Europe PMC téléchargés dans `corpus/raw/epmc/` (`python corpus/fetch_corpus.py`)
- [x] 2 PDF publics téléchargés dans `corpus/raw/web/` : fiche HAS d'écoconception et étude SusQI d'Imperial College sur la hernie
- [ ] 4 PDF à télécharger à la main dans `corpus/raw/manual/`, car les sites bloquent le téléchargement automatique. Voir `corpus/manifest.json` pour les liens.
  - [ ] `sfar_ecoconception_parcours.pdf` : SFAR, écoconception des parcours (2024)
  - [ ] `sfar_reduction_impact_ag.pdf` : SFAR, réduire l'impact de l'anesthésie générale (2023)
  - [ ] `shift_project_sante.pdf` : The Shift Project, décarboner la santé
  - [ ] `ipcc_ar6_ch7_sm.pdf` : GIEC AR6, chapitre 7, annexe
- [x] Index par mots-clés construit (`cd backend && python -m hippo.rag build`) : 24 documents, 1 561 passages
- [ ] Vecteurs calculés pour la recherche par le sens (`python -m hippo.rag embed`) : 800 sur 1 561, la suite est limitée par le quota gratuit Gemini (30 000 tokens par minute)
- [ ] Index et vecteurs reconstruits une fois les 4 PDF ajoutés

### Backend (API)
- [x] Environnement virtuel créé dans `backend/.venv`
- [x] Dépendances installées (`pip install -e ".[dev]"`)
- [x] 54 tests au vert (`python -m pytest`), dont le stockage PostgreSQL
- [x] Fichier `backend/.env` créé, jamais commité
  - [x] `OPENROUTER_API_KEY` renseignée
  - [x] `GEMINI_API_KEY` renseignée (secours)
  - [x] `HIPPO_MODEL=dots-studio/dots-3-note-preview:free`
  - [ ] `HIPPO_LLM_PROVIDER=openrouter` à écrire explicitement. Il est vide pour l'instant ; OpenRouter est quand même choisi d'après la clé présente.
- [x] API lancée : `uvicorn hippo.api.main:app --reload --port 8000`
- [x] http://localhost:8000/api/sante affiche `openrouter`, le modèle Dots, `"stockage": "PostgreSQL"` et `"recherche": "hybride"`

### Base de données
- [x] PostgreSQL 17 + pgvector dans Docker (port 5433 du poste)
- [x] Migrations versionnées appliquées au démarrage (`backend/hippo/store/migrations/`)
- [x] Décisions, valeurs locales et conversations enregistrées et relues après redémarrage
- [ ] Sauvegarde de la base planifiée (`docker compose exec db pg_dump -U hippo hippo > sauvegarde.sql`)

### Frontend (interface)
- [x] Dépendances installées (`cd frontend && npm install`)
- [x] Lint et build sans erreur
- [x] Interface lancée : `npm run dev`, puis http://localhost:3000
- [x] Scénario de démonstration : bouton « Charger le scénario de démo » dans le menu de gauche
- [x] Décisions signées (« Vous êtes ») et partagées entre les postes
- [x] Onglet Données locales : saisie des valeurs du service, historique, retour à l'hypothèse

### Assistant IA
- [x] Testé de bout en bout avec Dots3-Note sur OpenRouter : réponses en 16 à 37 s, chiffres et citations contrôlés
- [x] Conversations enregistrées en base
- [ ] Testé de bout en bout avec Gemini 3.8 Flash : le modèle était surchargé chez Google pendant le test
- [ ] Choisir le modèle du jour J et faire 5 questions de répétition la veille

---

## 2. Données : ce qu'on a, ce qu'il faut obtenir

Le calcul repose aujourd'hui à **87 % sur des hypothèses**. Chaque valeur réelle obtenue auprès de l'établissement rend le résultat plus crédible.

- Les **paramètres du service** (distances, énergie, volumes) se saisissent dans l'onglet **Données locales** de l'interface, avec leur origine : pas besoin de toucher au code. À elle seule, la distance réelle domicile–hôpital fait passer la part d'hypothèses de 87 % à environ 22 %.
- Les **facteurs d'émission** et les **sources** restent dans `backend/hippo/data/`, car ils sont communs à tous les établissements.

### Facteurs d'émission (`facteurs.json`)

| Facteur | Valeur | Source | État |
|---|---|---|---|
| Voiture, par km | 0,256 kgCO2e | ADEME Base Carbone | ✅ sourcé |
| Électricité, par kWh | 0,0519 kgCO2e | ADEME Base Carbone | ✅ sourcé |
| Gaz naturel, par kWh | 0,243 kgCO2e | ADEME Base Carbone | ✅ sourcé |
| Médicaments, par euro | 0,194 kgCO2e | ADEME Base Carbone (ratio monétaire) | ✅ sourcé |
| Sévoflurane 2 L/min, par heure | 14,5 kgCO2e | Drew 2021 | ✅ sourcé |
| Sévoflurane 1 L/min, par heure | 7 kgCO2e | Drew 2021 | ✅ sourcé |
| Propofol (AIVOC), par heure | 0,5 kgCO2e | Drew 2021 | ✅ sourcé |
| Produits du bloc, hernie | 11,7 kgCO2e | Rizan 2023 | ✅ sourcé |
| Bilan sanguin standard | 0,235 kgCO2e | Spoyalo 2023 | ✅ sourcé |
| Anesthésie locale, par intervention | 0,2 kgCO2e | hypothèse de l'équipe | ⬜ à sourcer |
| ECG | 0,1 kgCO2e | hypothèse de l'équipe | ⬜ à sourcer |
| Téléconsultation | 0,1 kgCO2e | ordre de grandeur Holmner 2014 | ⬜ à confirmer |

### Paramètres du parcours (`parcours_hernie.json`)

Ce sont les données locales qui pèsent le plus. À demander au service, aux services techniques et au DIM.

| Paramètre | Valeur actuelle | Fourchette | Qui peut fournir la vraie valeur | Obtenu |
|---|---|---|---|---|
| Distance domicile–hôpital (aller) | 20 km | 10–40 | DIM ou cadre : distance médiane d'après les codes postaux des patients | ⬜ |
| Distance domicile–laboratoire | 5 km | 2–15 | estimation de l'équipe | ⬜ |
| Durée d'anesthésie | 1 h | 0,75–1,5 | anesthésistes, logiciel de bloc | ⬜ |
| Électricité du bloc par intervention | 20 kWh | 10–40 | services techniques | ⬜ |
| Électricité de l'unité ambulatoire par patient | 15 kWh | 8–30 | services techniques | ⬜ |
| Chauffage au gaz de l'unité par patient | 20 kWh | 10–40 | services techniques | ⬜ |
| Part des patients ASA 3 ou plus | 20 % | 10–30 % | anesthésistes, DIM | ⬜ |
| Montant des antalgiques à la sortie | 10 € | 5–20 | pharmacie | ⬜ |
| Part de l'ordonnance conservée après ajustement | 60 % | 40–80 % | chirurgiens, pharmacie | ⬜ |
| Part de l'empreinte gardée avec un kit optimisé | 70 % | 58–77 % | Rizan 2023 | ✅ sourcé |
| Cures de hernie inguinale par an | 250 | — | DIM, ou Open CCAM (ATIH) par établissement | ⬜ |

### Pratiques actuelles du service (pour coller au terrain)
- [ ] Type d'anesthésie le plus courant : générale avec halogéné, AIVOC, rachianesthésie ou locale
- [ ] Débit de gaz frais habituel en entretien
- [ ] Bilan préopératoire prescrit en routine ou ciblé
- [ ] Nombre de venues avant l'intervention (consultation chirurgien, anesthésiste, examens)
- [ ] Contenu du kit opératoire et textiles (usage unique ou réutilisables)
- [ ] Modalité du suivi à J+30 (présentiel, téléphone, téléconsultation)

### Sources à vérifier (`sources.json`)
- [x] HerniaSurge 2018 et 2023, Rizan 2023, Drew 2021, Spoyalo 2023, ADEME : vérifiées
- [ ] `sfar2012_examens` : recommandation SFAR 2012 sur les examens préopératoires (référence exacte et lien)
- [ ] `sfar2023_ag` : SFAR 2023, réduction de l'impact de l'anesthésie générale
- [ ] `sfar2024_parcours` : SFAR 2024, écoconception des parcours
- [ ] Numéro du critère HAS de certification cité (2.4-04)

---

## 3. Fonctionnalités du prototype

- [x] Corpus open source et pipeline RAG (BM25, passages citables avec licence)
- [x] Moteur de calcul : 3 scénarios (bas, central, haut), gains par alternative, conflits, extrapolation annuelle, part d'hypothèses
- [x] Bibliothèque de 9 alternatives : 5 validées par une recommandation, 4 à discuter en équipe
- [x] Fiche action imprimable en PDF
- [x] API FastAPI
- [x] Interface Next.js : parcours, comparaison, plan d'action, références, panneau assistant
- [x] Assistant avec outils et garde-fous : citations contrôlées, chiffres tracés, blocage si non sourcé
- [x] Plusieurs fournisseurs de modèle : Claude, OpenRouter, Mistral, Gemini, Ollama
- [x] Base de données PostgreSQL, décisions partagées et historisées, valeurs locales par équipe
- [x] Recherche hybride : mots-clés et sens (une question en français trouve les passages en anglais)
- [x] Lancement Docker en une commande
- [ ] Affichage progressif des étapes de l'assistant pendant qu'il réfléchit (facultatif)
- [ ] Authentification des utilisateurs (aujourd'hui, le nom saisi n'est pas vérifié)
- [ ] Hébergement sur un serveur accessible à l'équipe (HTTPS)

---

## 4. Préparer la démo

- [x] Scénario de démonstration : 88,9 → 51,4 kgCO2e par patient, soit −42 %
- [ ] Hypothèses relues avec le référent médical
- [ ] Remplacer « CHU de démonstration » par le vrai nom de l'établissement si on a son accord
- [ ] Script du pitch : problème, parcours, alternatives, assistant, fiche action
- [ ] Vidéo de secours enregistrée, au cas où le modèle gratuit soit lent ou surchargé
- [ ] Répétition complète chronométrée
