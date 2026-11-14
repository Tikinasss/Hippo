"""Données propres à chaque équipe : valeurs locales, décisions, conversations.

Les valeurs locales et les décisions sont des journaux en ajout seul : l'état courant
est la dernière entrée par paramètre (ou par alternative), et l'historique complet
reste consultable (qui a saisi ou décidé quoi, et quand).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Equipe(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")
    etablissement: str = Field(..., min_length=1, max_length=200)
    service: str = Field(..., min_length=1, max_length=200)


class ValeurLocale(BaseModel):
    """Valeur réelle d'un paramètre du parcours pour une équipe ; `actif=False` revient à l'hypothèse."""

    parametre: str
    valeur: float | None = None
    bas: float | None = None
    haut: float | None = None
    origine: str | None = Field(None, max_length=500)
    auteur: str = Field(..., min_length=1, max_length=120)
    actif: bool = True
    date: str = Field(default_factory=maintenant)

    @model_validator(mode="after")
    def _coherence(self) -> "ValeurLocale":
        if not self.actif:
            return self
        if self.valeur is None:
            raise ValueError("une valeur est requise")
        if not self.origine:
            raise ValueError("indiquez l'origine de la valeur (ex. DIM, services techniques)")
        bas = self.valeur if self.bas is None else self.bas
        haut = self.valeur if self.haut is None else self.haut
        if not (bas <= self.valeur <= haut):
            raise ValueError("il faut bas <= valeur <= haut")
        return self


StatutDecision = Literal["retenue", "a_discuter", "aucune"]


class Decision(BaseModel):
    alternative: str
    statut: StatutDecision
    auteur: str = Field(..., min_length=1, max_length=120)
    commentaire: str | None = Field(None, max_length=1000)
    date: str = Field(default_factory=maintenant)


def derniers(entrees: list, cle: str) -> dict:
    """Dernière entrée par clé (les journaux sont dans l'ordre chronologique)."""
    etat: dict = {}
    for e in entrees:
        etat[getattr(e, cle)] = e
    return etat
