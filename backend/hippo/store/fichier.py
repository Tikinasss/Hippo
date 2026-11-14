"""Stockage sans base de données : en mémoire, éventuellement sauvegardé dans un fichier JSON.

Pour le développement et les tests, ou un poste unique sans Docker. Une seule
instance de l'API doit écrire dans le fichier.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from .modeles import Decision, Equipe, ValeurLocale, derniers


class StockageFichier:
    nom = "fichier"

    def __init__(self, chemin: Path | None = None) -> None:
        self.chemin = chemin
        self._verrou = threading.RLock()
        self._equipes: dict[str, Equipe] = {}
        self._valeurs: dict[str, list[ValeurLocale]] = {}
        self._decisions: dict[str, list[Decision]] = {}
        self._conversations: dict[str, dict] = {}
        if chemin and chemin.exists():
            self._charger()

    @property
    def nom_complet(self) -> str:
        return f"fichier ({self.chemin})" if self.chemin else "mémoire"

    # --- persistance -------------------------------------------------------------------

    def _charger(self) -> None:
        d = json.loads(self.chemin.read_text(encoding="utf-8"))
        self._equipes = {e["id"]: Equipe.model_validate(e) for e in d.get("equipes", [])}
        self._valeurs = {k: [ValeurLocale.model_validate(v) for v in vs] for k, vs in d.get("valeurs", {}).items()}
        self._decisions = {k: [Decision.model_validate(v) for v in vs] for k, vs in d.get("decisions", {}).items()}
        self._conversations = d.get("conversations", {})

    def _sauver(self) -> None:
        if not self.chemin:
            return
        d = {
            "equipes": [e.model_dump() for e in self._equipes.values()],
            "valeurs": {k: [v.model_dump() for v in vs] for k, vs in self._valeurs.items()},
            "decisions": {k: [v.model_dump() for v in vs] for k, vs in self._decisions.items()},
            "conversations": self._conversations,
        }
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.chemin.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, self.chemin)  # écriture atomique

    # --- équipes -----------------------------------------------------------------------

    def equipes(self) -> list[Equipe]:
        return list(self._equipes.values())

    def equipe(self, equipe_id: str) -> Equipe | None:
        return self._equipes.get(equipe_id)

    def creer_equipe(self, e: Equipe) -> Equipe:
        with self._verrou:
            if e.id not in self._equipes:
                self._equipes[e.id] = e
                self._sauver()
            return self._equipes[e.id]

    # --- valeurs locales ---------------------------------------------------------------

    def historique_valeurs(self, equipe_id: str) -> list[ValeurLocale]:
        return list(self._valeurs.get(equipe_id, []))

    def valeurs_locales(self, equipe_id: str) -> list[ValeurLocale]:
        return [v for v in derniers(self.historique_valeurs(equipe_id), "parametre").values() if v.actif]

    def ajouter_valeur(self, equipe_id: str, v: ValeurLocale) -> None:
        with self._verrou:
            self._valeurs.setdefault(equipe_id, []).append(v)
            self._sauver()

    # --- décisions ---------------------------------------------------------------------

    def historique_decisions(self, equipe_id: str) -> list[Decision]:
        return list(self._decisions.get(equipe_id, []))

    def decisions(self, equipe_id: str) -> dict[str, Decision]:
        return {k: d for k, d in derniers(self.historique_decisions(equipe_id), "alternative").items()
                if d.statut != "aucune"}

    def ajouter_decision(self, equipe_id: str, d: Decision) -> None:
        with self._verrou:
            self._decisions.setdefault(equipe_id, []).append(d)
            self._sauver()

    # --- conversations -----------------------------------------------------------------

    def conversation(self, conversation_id: str) -> dict | None:
        return self._conversations.get(conversation_id)

    def enregistrer_conversation(self, conversation_id: str, equipe_id: str, donnees: dict) -> None:
        with self._verrou:
            self._conversations[conversation_id] = {**donnees, "equipe": equipe_id}
            self._sauver()
