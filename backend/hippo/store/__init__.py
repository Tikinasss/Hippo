"""Stockage des données d'équipe : PostgreSQL si DATABASE_URL est défini, sinon fichier JSON local.

    DATABASE_URL   postgresql://hippo:hippo@localhost:5433/hippo
    HIPPO_STORE    postgres | fichier | memoire   (défaut : postgres si DATABASE_URL, sinon fichier)
    HIPPO_STORE_FICHIER  chemin du fichier JSON (défaut : backend/var/hippo.json)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from .. import config
from .fichier import StockageFichier
from .modeles import Decision, Equipe, StatutDecision, ValeurLocale, maintenant

EQUIPE_DEFAUT = Equipe(
    id=os.environ.get("HIPPO_EQUIPE_ID", "demo"),
    etablissement=os.environ.get("HIPPO_EQUIPE_ETABLISSEMENT", "CHU de démonstration"),
    service=os.environ.get("HIPPO_EQUIPE_SERVICE", "Chirurgie ambulatoire"),
)


class Stockage(Protocol):
    nom: str
    nom_complet: str

    def equipes(self) -> list[Equipe]: ...
    def equipe(self, equipe_id: str) -> Equipe | None: ...
    def creer_equipe(self, e: Equipe) -> Equipe: ...
    def historique_valeurs(self, equipe_id: str) -> list[ValeurLocale]: ...
    def valeurs_locales(self, equipe_id: str) -> list[ValeurLocale]: ...
    def ajouter_valeur(self, equipe_id: str, v: ValeurLocale) -> None: ...
    def historique_decisions(self, equipe_id: str) -> list[Decision]: ...
    def decisions(self, equipe_id: str) -> dict[str, Decision]: ...
    def ajouter_decision(self, equipe_id: str, d: Decision) -> None: ...
    def conversation(self, conversation_id: str) -> dict | None: ...
    def enregistrer_conversation(self, conversation_id: str, equipe_id: str, donnees: dict) -> None: ...


def creer_stockage() -> Stockage:
    url = os.environ.get("DATABASE_URL")
    choix = os.environ.get("HIPPO_STORE") or ("postgres" if url else "fichier")
    if choix == "postgres":
        if not url:
            raise RuntimeError("HIPPO_STORE=postgres demande DATABASE_URL")
        from .postgres import StockagePostgres  # psycopg n'est importé que s'il sert

        s: Stockage = StockagePostgres(url)
    elif choix == "memoire":
        s = StockageFichier(None)
    else:
        s = StockageFichier(Path(os.environ.get("HIPPO_STORE_FICHIER", config.BACKEND_DIR / "var" / "hippo.json")))
    s.creer_equipe(EQUIPE_DEFAUT)
    return s


__all__ = ["Stockage", "StockageFichier", "Equipe", "ValeurLocale", "Decision", "StatutDecision",
           "EQUIPE_DEFAUT", "creer_stockage", "maintenant"]
