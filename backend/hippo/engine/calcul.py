"""Moteur de calcul d'impact : déterministe, sans LLM.

Chaque résultat est une fourchette calculée sur trois scénarios cohérents :
- « bas »     : bornes basses de tous les facteurs et paramètres,
- « central » : valeurs centrales,
- « haut »    : bornes hautes.
Un gain est la différence avant / après **dans le même scénario**, ce qui évite
de combiner une borne basse d'un côté avec une borne haute de l'autre.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .models import Activite, Alternative, Etape
from .repository import Referentiel, referentiel

SCENARIOS = ("bas", "central", "haut")


class ConflitAlternatives(ValueError):
    """Deux alternatives retenues modifient le même poste d'une étape."""


@dataclass(frozen=True)
class Fourchette:
    bas: float
    central: float
    haut: float

    @classmethod
    def zero(cls) -> "Fourchette":
        return cls(0.0, 0.0, 0.0)

    def __add__(self, o: "Fourchette") -> "Fourchette":
        return Fourchette(self.bas + o.bas, self.central + o.central, self.haut + o.haut)

    def __sub__(self, o: "Fourchette") -> "Fourchette":
        return Fourchette(self.bas - o.bas, self.central - o.central, self.haut - o.haut)

    def __mul__(self, k: float) -> "Fourchette":
        return Fourchette(self.bas * k, self.central * k, self.haut * k)

    def ordonnee(self) -> "Fourchette":
        """Pour un gain, le scénario « bas » n'est pas forcément le plus petit : on remet dans l'ordre."""
        lo, hi = sorted((self.bas, self.haut))
        return Fourchette(min(lo, self.central), self.central, max(hi, self.central))

    def arrondie(self, n: int = 1) -> dict:
        return {"bas": round(self.bas, n), "central": round(self.central, n), "haut": round(self.haut, n)}


@dataclass
class LigneImpact:
    cle: str
    libelle: str
    facteur: str
    quantite: float
    unite: str
    impact: Fourchette
    hypothese: bool
    source: str

    def to_dict(self) -> dict:
        return {
            "cle": self.cle,
            "libelle": self.libelle,
            "facteur": self.facteur,
            "quantite": round(self.quantite, 3),
            "unite": self.unite,
            "impact_kgco2e": self.impact.arrondie(2),
            "hypothese": self.hypothese,
            "source": self.source,
        }


@dataclass
class ImpactEtape:
    etape: Etape
    lignes: list[LigneImpact]
    alternatives: list[str] = field(default_factory=list)

    @property
    def total(self) -> Fourchette:
        t = Fourchette.zero()
        for l in self.lignes:
            t = t + l.impact
        return t

    def to_dict(self, total_parcours: float | None = None) -> dict:
        d = {
            "id": self.etape.id,
            "ordre": self.etape.ordre,
            "jour": self.etape.jour,
            "titre": self.etape.titre,
            "acteur": self.etape.acteur,
            "pratique_actuelle": self.etape.pratique_actuelle,
            "alternatives_appliquees": self.alternatives,
            "impact_kgco2e": self.total.arrondie(1),
            "lignes": [l.to_dict() for l in self.lignes],
        }
        if total_parcours:
            d["part_du_total"] = round(self.total.central / total_parcours, 3)
        return d


class Calculateur:
    def __init__(self, ref: Referentiel | None = None) -> None:
        self.ref = ref or referentiel()

    # --- briques -------------------------------------------------------------------

    def _quantite(self, a: Activite, scenario: str) -> float:
        params = self.ref.parametres
        attr = "valeur" if scenario == "central" else scenario
        return a.quantite * math.prod(getattr(params[p], attr) for p in a.parametres)

    def ligne(self, a: Activite) -> LigneImpact:
        f = self.ref.facteurs[a.facteur]
        params = self.ref.parametres
        valeurs = {}
        for sc in SCENARIOS:
            fattr = "valeur" if sc == "central" else sc
            valeurs[sc] = self._quantite(a, sc) * getattr(f, fattr)
        hypothese = f.statut == "hypothese" or any(params[p].statut == "hypothese" for p in a.parametres)
        return LigneImpact(
            cle=a.cle,
            libelle=a.libelle,
            facteur=f.id,
            quantite=self._quantite(a, "central"),
            unite=a.unite,
            impact=Fourchette(**valeurs),
            hypothese=hypothese,
            source=f.source,
        )

    def impact_etape(self, etape: Etape, alternatives: list[Alternative] = ()) -> ImpactEtape:
        remplacements: dict[str, list[Activite]] = {}
        for alt in alternatives:
            for cle, activites in alt.remplace.items():
                if cle in remplacements:
                    autre = next(a.id for a in alternatives if cle in a.remplace and a is not alt)
                    raise ConflitAlternatives(
                        f"« {alt.titre} » et « {self.ref.alternatives[autre].titre} » modifient le même poste "
                        f"({cle}) de l'étape {etape.titre} : il faut choisir l'une ou l'autre."
                    )
                remplacements[cle] = activites
        activites: list[Activite] = []
        for a in etape.activites:
            if a.cle in remplacements:
                activites.extend(remplacements.pop(a.cle))
            else:
                activites.append(a)
        return ImpactEtape(etape=etape, lignes=[self.ligne(a) for a in activites], alternatives=[a.id for a in alternatives])

    # --- parcours ------------------------------------------------------------------

    def parcours(self, retenues: list[str] = ()) -> dict:
        """Impact du parcours actuel et du parcours optimisé avec les alternatives `retenues`."""
        inconnues = [r for r in retenues if r not in self.ref.alternatives]
        if inconnues:
            raise KeyError(f"alternatives inconnues : {', '.join(inconnues)}")
        alts = [self.ref.alternatives[r] for r in dict.fromkeys(retenues)]

        avant = [self.impact_etape(e) for e in self.ref.parcours.etapes]
        apres = [self.impact_etape(e, [a for a in alts if a.etape == e.id]) for e in self.ref.parcours.etapes]
        total_avant = sum((i.total for i in avant), Fourchette.zero())
        total_apres = sum((i.total for i in apres), Fourchette.zero())
        evite = (total_avant - total_apres).ordonnee()

        principal = max(avant, key=lambda i: i.total.central)
        n_annuel = self.ref.parametres["interventions_annuelles"].valeur
        part_hyp = sum(l.impact.central for i in avant for l in i.lignes if l.hypothese) / total_avant.central

        return {
            "parcours": {"id": self.ref.parcours.id, "titre": self.ref.parcours.titre, "perimetre": self.ref.parcours.perimetre},
            "unite": "kgCO2e par patient",
            "avant": {
                "total": total_avant.arrondie(1),
                "etapes": [i.to_dict(total_avant.central) for i in avant],
            },
            "apres": {
                "total": total_apres.arrondie(1),
                "etapes": [i.to_dict(total_apres.central) for i in apres],
            },
            "evite": evite.arrondie(1),
            "reduction_pct": round(100 * evite.central / total_avant.central, 1),
            "poste_principal": {
                "etape": principal.etape.id,
                "titre": principal.etape.titre,
                "part": round(principal.total.central / total_avant.central, 3),
            },
            "annuel": {
                "interventions": n_annuel,
                "avant_tco2e": (total_avant * (n_annuel / 1000)).arrondie(2),
                "apres_tco2e": (total_apres * (n_annuel / 1000)).arrondie(2),
                "evite_tco2e": (evite * (n_annuel / 1000)).arrondie(2),
            },
            "retenues": [a.id for a in alts],
            "part_hypotheses": round(part_hyp, 3),
        }

    def gain_alternative(self, alt_id: str) -> dict:
        """Gain d'une alternative seule, par rapport à la pratique actuelle de son étape."""
        alt = self.ref.alternatives[alt_id]
        etape = self.ref.etape(alt.etape)
        avant = self.impact_etape(etape)
        apres = self.impact_etape(etape, [alt])
        gain = (avant.total - apres.total).ordonnee()
        return {
            "alternative": alt.id,
            "etape": etape.id,
            "avant_kgco2e": avant.total.arrondie(1),
            "apres_kgco2e": apres.total.arrondie(1),
            "gain_kgco2e": gain.arrondie(1),
        }
