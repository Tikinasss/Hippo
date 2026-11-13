"""Modèles de données du parcours, des facteurs d'émission et des alternatives."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Source(BaseModel):
    id: str
    citation: str
    url: str | None = None
    type: Literal["recommandation", "essai", "revue", "etude", "base_donnees", "document"]
    corpus_id: str | None = Field(None, description="Identifiant du document dans le corpus RAG, s'il y est")
    verifie: bool = Field(True, description="False si le texte n'a pas encore été lu par l'équipe")
    note: str | None = None


class Facteur(BaseModel):
    """Facteur d'émission : `valeur` kgCO2e par unité, avec fourchette [bas, haut]."""

    id: str
    libelle: str
    valeur: float
    bas: float
    haut: float
    unite: str = Field(..., description="Unité du dénominateur, ex. « km », « h », « kWh »")
    source: str
    statut: Literal["source", "hypothese"]
    note: str | None = None

    @model_validator(mode="after")
    def _ordre(self) -> "Facteur":
        if not (self.bas <= self.valeur <= self.haut):
            raise ValueError(f"facteur {self.id} : il faut bas <= valeur <= haut")
        return self


class Parametre(BaseModel):
    """Hypothèse du parcours (distance, durée, proportion…) avec sa fourchette."""

    id: str
    libelle: str
    valeur: float
    bas: float
    haut: float
    unite: str
    statut: Literal["source", "hypothese"] = "hypothese"
    source: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _ordre(self) -> "Parametre":
        if not (self.bas <= self.valeur <= self.haut):
            raise ValueError(f"paramètre {self.id} : il faut bas <= valeur <= haut")
        return self


class Activite(BaseModel):
    """Une ligne de calcul : quantité × facteur. La quantité vaut `quantite` × produit des `parametres`."""

    cle: str = Field(..., description="Poste de l'étape (trajet, anesthesie…), utilisé par les alternatives")
    libelle: str
    facteur: str
    quantite: float = 1.0
    parametres: list[str] = Field(default_factory=list)
    unite: str = Field(..., description="Doit correspondre à l'unité du facteur")


class Etape(BaseModel):
    id: str
    ordre: int
    jour: str
    titre: str
    acteur: str
    pratique_actuelle: str
    activites: list[Activite]


class Parcours(BaseModel):
    id: str
    titre: str
    description: str
    perimetre: str
    parametres: list[Parametre]
    etapes: list[Etape]


class Alternative(BaseModel):
    id: str
    etape: str
    titre: str
    sous_titre: str
    statut: Literal["validee", "a_discuter"] = Field(
        ..., description="validee : recommandation professionnelle ; a_discuter : preuve partielle ou choix d'organisation"
    )
    niveau_preuve: str
    securite: Literal["equivalente", "a_evaluer"]
    conditions: str | None = None
    vigilance: list[str] = Field(default_factory=list)
    effets_indirects: list[str] = Field(default_factory=list)
    indicateur: str | None = Field(None, description="Indicateur de suivi pour le plan d'action")
    sources: list[str] = Field(..., min_length=1, description="Pas de suggestion sans source")
    remplace: dict[str, list[Activite]] = Field(
        ..., description="Pour chaque poste (cle) de l'étape, les nouvelles activités ; liste vide = poste supprimé"
    )
