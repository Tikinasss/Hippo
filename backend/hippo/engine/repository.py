"""Chargement et contrôle de cohérence des données sourcées (JSON)."""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Protocol

from .. import config
from .models import Activite, Alternative, Facteur, Parametre, Parcours, Source


class DonneesInvalides(ValueError):
    pass


class ValeurLocaleLike(Protocol):
    parametre: str
    valeur: float | None
    bas: float | None
    haut: float | None
    origine: str | None
    auteur: str
    date: str


@dataclass(frozen=True)
class Referentiel:
    parcours: Parcours
    facteurs: dict[str, Facteur]
    sources: dict[str, Source]
    alternatives: dict[str, Alternative]

    @property
    def parametres(self) -> dict[str, Parametre]:
        return {p.id: p for p in self.parcours.parametres}

    def etape(self, etape_id: str):
        return next(e for e in self.parcours.etapes if e.id == etape_id)

    def avec_valeurs_locales(self, valeurs: Iterable[ValeurLocaleLike]) -> "Referentiel":
        """Référentiel où les hypothèses sont remplacées par les valeurs réelles saisies par l'équipe."""
        par_id = {v.parametre: v for v in valeurs}
        if not par_id:
            return self
        inconnus = set(par_id) - set(self.parametres)
        if inconnus:
            raise KeyError(f"paramètres inconnus : {', '.join(sorted(inconnus))}")
        params = []
        for p in self.parcours.parametres:
            v = par_id.get(p.id)
            if v is not None:
                p = Parametre.model_validate({
                    **p.model_dump(), "valeur": v.valeur,
                    "bas": v.valeur if v.bas is None else v.bas, "haut": v.valeur if v.haut is None else v.haut,
                    "statut": "local", "source": None, "origine": v.origine, "saisi_par": v.auteur, "saisi_le": v.date,
                })
            params.append(p)
        return replace(self, parcours=self.parcours.model_copy(update={"parametres": params}))

    def alternatives_de(self, etape_id: str) -> list[Alternative]:
        return [a for a in self.alternatives.values() if a.etape == etape_id]

    def verifier(self) -> None:
        """Lève DonneesInvalides si une référence est cassée ou une unité incohérente."""
        erreurs: list[str] = []
        params = self.parametres

        def verifier_activite(a: Activite, ou: str) -> None:
            f = self.facteurs.get(a.facteur)
            if f is None:
                erreurs.append(f"{ou} : facteur inconnu « {a.facteur} »")
            elif f.unite != a.unite:
                erreurs.append(f"{ou} : unité « {a.unite} » incompatible avec le facteur {f.id} (par {f.unite})")
            for p in a.parametres:
                if p not in params:
                    erreurs.append(f"{ou} : paramètre inconnu « {p} »")

        for f in self.facteurs.values():
            if f.source not in self.sources:
                erreurs.append(f"facteur {f.id} : source inconnue « {f.source} »")
        for p in params.values():
            if p.source and p.source not in self.sources:
                erreurs.append(f"paramètre {p.id} : source inconnue « {p.source} »")
        etapes = {e.id: e for e in self.parcours.etapes}
        for e in etapes.values():
            for a in e.activites:
                verifier_activite(a, f"étape {e.id}")
        for alt in self.alternatives.values():
            etape = etapes.get(alt.etape)
            if etape is None:
                erreurs.append(f"alternative {alt.id} : étape inconnue « {alt.etape} »")
                continue
            cles = {a.cle for a in etape.activites}
            for cle, activites in alt.remplace.items():
                if cle not in cles:
                    erreurs.append(f"alternative {alt.id} : poste « {cle} » absent de l'étape {etape.id}")
                for a in activites:
                    verifier_activite(a, f"alternative {alt.id}")
            for s in alt.sources:
                if s not in self.sources:
                    erreurs.append(f"alternative {alt.id} : source inconnue « {s} »")
        if erreurs:
            raise DonneesInvalides("\n".join(erreurs))


def _lire(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def charger(data_dir: Path = config.DATA_DIR) -> Referentiel:
    ref = Referentiel(
        parcours=Parcours.model_validate(_lire(data_dir / "parcours_hernie.json")),
        facteurs={f["id"]: Facteur.model_validate(f) for f in _lire(data_dir / "facteurs.json")},
        sources={s["id"]: Source.model_validate(s) for s in _lire(data_dir / "sources.json")},
        alternatives={a["id"]: Alternative.model_validate(a) for a in _lire(data_dir / "alternatives.json")},
    )
    ref.verifier()
    return ref


@lru_cache(maxsize=1)
def referentiel() -> Referentiel:
    return charger()
