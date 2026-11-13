"""Garde-fous appliqués à la réponse finale de l'assistant.

1. Pas de suggestion sans source : chaque marqueur [S:id] doit désigner une source
   réellement renvoyée par un outil, et une réponse qui avance un chiffre ou une
   recommandation doit en citer au moins une.
2. Pas de chiffre inventé : tout nombre exprimé en CO2e ou en pourcentage doit
   correspondre (à l'arrondi près) à un nombre renvoyé par un outil.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MARQUEUR = re.compile(r"\[S:([^\]\s]+)\]")
_CHIFFRE_CO2 = re.compile(
    r"(?<![\w.,])[−-]?(\d+(?:[.,]\d+)?)\s*(?:%|(?:k?g|t)\s*(?:de\s+)?CO\s*(?:2|₂)e?)", re.IGNORECASE
)
_RECOMMANDATION = re.compile(r"recommand|preuve|validée|sécurité équivalente|guideline|SFAR|HAS|HerniaSurge", re.IGNORECASE)


@dataclass
class Verification:
    citations_valides: list[str] = field(default_factory=list)
    citations_inconnues: list[str] = field(default_factory=list)
    chiffres_non_traces: list[str] = field(default_factory=list)
    sans_source: bool = False

    @property
    def ok(self) -> bool:
        return not (self.citations_inconnues or self.chiffres_non_traces or self.sans_source)

    def consigne_correction(self) -> str:
        problemes = []
        if self.citations_inconnues:
            problemes.append(f"ces identifiants de source n'ont été renvoyés par aucun outil : {', '.join(self.citations_inconnues)}")
        if self.chiffres_non_traces:
            problemes.append(f"ces chiffres ne proviennent d'aucun résultat d'outil : {', '.join(self.chiffres_non_traces)}")
        if self.sans_source:
            problemes.append("la réponse avance des chiffres ou des recommandations sans aucune citation [S:id]")
        return (
            "[Contrôle automatique Hippo] La réponse précédente ne peut pas être affichée : "
            + " ; ".join(problemes)
            + ". Réécris-la en utilisant les outils pour obtenir chiffres et sources, en citant chaque "
            "affirmation avec [S:id], ou retire ce qui ne peut pas être sourcé."
        )

    def to_dict(self) -> dict:
        return {"ok": self.ok, "citations_valides": self.citations_valides,
                "citations_inconnues": self.citations_inconnues,
                "chiffres_non_traces": self.chiffres_non_traces, "sans_source": self.sans_source}


def _trace(valeur: float, nombres: set[float]) -> bool:
    for n in nombres:
        for candidat in (n, abs(n), round(n), round(n, 1), abs(round(n)), abs(round(n, 1))):
            if abs(candidat - valeur) <= max(0.051, 0.01 * abs(candidat)):
                return True
    # pourcentages exprimés à partir d'une proportion (0.306 -> 31 %)
    return any(abs(100 * n - valeur) <= 0.6 for n in nombres if 0 <= n <= 1)


def verifier(texte: str, sources_vues: set[str], nombres: set[float]) -> Verification:
    v = Verification()
    for sid in dict.fromkeys(MARQUEUR.findall(texte)):
        (v.citations_valides if sid in sources_vues else v.citations_inconnues).append(sid)
    for m in _CHIFFRE_CO2.finditer(texte):
        valeur = float(m.group(1).replace(",", "."))
        if not _trace(valeur, nombres):
            v.chiffres_non_traces.append(m.group(0).strip())
    substantielle = bool(_CHIFFRE_CO2.search(texte) or _RECOMMANDATION.search(texte))
    v.sans_source = substantielle and not v.citations_valides
    return v


def numeroter(texte: str, sources_vues: dict[str, dict]) -> tuple[str, list[dict]]:
    """Remplace les marqueurs [S:id] par [1], [2]… et renvoie la liste des références."""
    ordre: dict[str, int] = {}

    def remplacer(m: re.Match) -> str:
        sid = m.group(1)
        if sid not in sources_vues:
            return ""
        ordre.setdefault(sid, len(ordre) + 1)
        return f"[{ordre[sid]}]"

    texte = MARQUEUR.sub(remplacer, texte)
    texte = re.sub(r"(\[\d+\])(?:\s*\1)+", r"\1", texte)
    refs = [{"numero": n, **sources_vues[sid]} for sid, n in ordre.items()]
    return texte, refs
