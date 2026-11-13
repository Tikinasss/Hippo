"""Outils de l'assistant : chaque chiffre vient du moteur de calcul, chaque source du référentiel ou du corpus.

`ContexteOutils` garde la trace de tout ce que les outils ont renvoyé pendant une
conversation (identifiants de sources, nombres) : c'est ce qui permet aux
garde-fous de vérifier la réponse finale.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field

from ..engine import Calculateur, ConflitAlternatives
from ..rag import load_index

_NOMBRE = re.compile(r"-?\d+(?:\.\d+)?")
THEMES = ["parcours_hernie", "parcours_global", "bloc_consommables", "bloc_anesthesie",
          "preop_biologie", "suivi_teleconsultation", "contexte"]


@dataclass
class ContexteOutils:
    calc: Calculateur
    sources_vues: dict[str, dict] = field(default_factory=dict)  # id -> {citation, url, type}
    nombres: set[float] = field(default_factory=set)
    fiche_url: str | None = None

    def noter_source(self, sid: str, citation: str, url: str | None, nature: str, extrait: str | None = None) -> None:
        self.sources_vues[sid] = {"id": sid, "citation": citation, "url": url, "nature": nature, "extrait": extrait}

    def noter_nombres(self, payload: object) -> None:
        for n in _NOMBRE.findall(json.dumps(payload, ensure_ascii=False)):
            self.nombres.add(float(n))

    def noter_source_referentiel(self, sid: str) -> dict:
        s = self.calc.ref.sources[sid]
        self.noter_source(sid, s.citation, s.url, "referentiel")
        return {"id": s.id, "citation": s.citation, "verifiee": s.verifie}


def definitions(calc: Calculateur) -> list[dict]:
    """Schémas JSON des outils (strict : arguments toujours valides)."""
    alt_ids = sorted(calc.ref.alternatives)
    etape_ids = [e.id for e in calc.ref.parcours.etapes]
    etapes_txt = ", ".join(f"{e.id} ({e.jour} {e.titre})" for e in calc.ref.parcours.etapes)
    return [
        {
            "name": "calculer_impact",
            "description": (
                "Calcule l'empreinte carbone du parcours de cure de hernie inguinale, avant et après les "
                "alternatives retenues, en kgCO2e par patient avec fourchette (bas, central, haut), plus "
                "l'extrapolation annuelle du service. Seule source autorisée pour un chiffre d'impact. "
                "Deux alternatives qui modifient le même poste d'une étape (ex. AIVOC et bas débit) ne peuvent "
                "pas être retenues ensemble : l'outil renvoie alors une erreur."
            ),
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "alternatives_retenues": {"type": "array", "items": {"type": "string", "enum": alt_ids},
                                              "description": "Identifiants des alternatives à appliquer ; liste vide = parcours actuel"},
                },
                "required": ["alternatives_retenues"],
                "additionalProperties": False,
            },
        },
        {
            "name": "chercher_alternatives",
            "description": (
                "Liste les alternatives documentées pour une étape du parcours (ou toutes) : statut "
                "(validée = recommandation professionnelle, à discuter = preuve partielle), sécurité, conditions, "
                f"vigilance, gain calculé et sources. Étapes : {etapes_txt}."
            ),
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {"etape": {"type": "string", "enum": [*etape_ids, "toutes"],
                                         "description": "Identifiant d'étape, ou « toutes »"}},
                "required": ["etape"],
                "additionalProperties": False,
            },
        },
        {
            "name": "expliquer_calcul",
            "description": (
                "Détaille le calcul d'une étape : chaque ligne (quantité × facteur d'émission), la valeur et la "
                "source de chaque facteur, les hypothèses utilisées. À utiliser pour « expliquer le calcul »."
            ),
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {"etape": {"type": "string", "enum": etape_ids}},
                "required": ["etape"],
                "additionalProperties": False,
            },
        },
        {
            "name": "chercher_sources",
            "description": (
                "Recherche plein texte dans le corpus de sources (recommandations HerniaSurge, SFAR, HAS, articles "
                "d'analyse de cycle de vie, essais). Le corpus est surtout en anglais : formuler la requête en "
                "anglais avec des mots-clés précis (ex. « local anaesthesia inguinal hernia recommendation »). "
                "Renvoie des extraits avec leur identifiant à citer."
            ),
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "requete_en_anglais": {"type": "string"},
                    "theme": {"type": "string", "enum": [*THEMES, "tous"],
                              "description": "Restreindre à un thème, ou « tous »"},
                },
                "required": ["requete_en_anglais", "theme"],
                "additionalProperties": False,
            },
        },
        {
            "name": "preparer_fiche_action",
            "description": (
                "Prépare la fiche action pour la certification HAS à partir des alternatives retenues par "
                "l'équipe et de celles mises en discussion. Renvoie le lien de la fiche (HTML imprimable en PDF)."
            ),
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "alternatives_retenues": {"type": "array", "items": {"type": "string", "enum": alt_ids}},
                    "alternatives_a_discuter": {"type": "array", "items": {"type": "string", "enum": alt_ids}},
                },
                "required": ["alternatives_retenues", "alternatives_a_discuter"],
                "additionalProperties": False,
            },
        },
    ]


# --- Exécution --------------------------------------------------------------------


def _calculer_impact(ctx: ContexteOutils, alternatives_retenues: list[str]) -> dict:
    r = ctx.calc.parcours(alternatives_retenues)
    etapes = []
    for av, ap in zip(r["avant"]["etapes"], r["apres"]["etapes"]):
        etapes.append({"etape": av["id"], "jour": av["jour"], "titre": av["titre"],
                       "avant": av["impact_kgco2e"], "apres": ap["impact_kgco2e"],
                       "part_du_total_avant": av["part_du_total"]})
    sources = sorted({f.source for f in ctx.calc.ref.facteurs.values()})
    return {
        "unite": r["unite"],
        "avant": r["avant"]["total"], "apres": r["apres"]["total"], "evite": r["evite"],
        "reduction_pct": r["reduction_pct"],
        "annuel": r["annuel"],
        "poste_principal": r["poste_principal"],
        "part_hypotheses": r["part_hypotheses"],
        "perimetre": r["parcours"]["perimetre"],
        "etapes": etapes,
        "sources_des_facteurs": [ctx.noter_source_referentiel(s) for s in sources],
    }


def _chercher_alternatives(ctx: ContexteOutils, etape: str) -> dict:
    ref = ctx.calc.ref
    alts = [a for a in ref.alternatives.values() if etape in (None, "toutes") or a.etape == etape]
    return {
        "alternatives": [
            {
                "id": a.id, "etape": a.etape, "titre": a.titre, "sous_titre": a.sous_titre,
                "statut": a.statut, "niveau_preuve": a.niveau_preuve, "securite": a.securite,
                "conditions": a.conditions, "vigilance": a.vigilance, "effets_indirects": a.effets_indirects,
                "gain_kgco2e_par_patient": ctx.calc.gain_alternative(a.id)["gain_kgco2e"],
                "sources": [ctx.noter_source_referentiel(s) for s in a.sources],
            }
            for a in alts
        ]
    }


def _expliquer_calcul(ctx: ContexteOutils, etape: str) -> dict:
    ref = ctx.calc.ref
    e = ref.etape(etape)
    impact = ctx.calc.impact_etape(e)
    lignes = []
    for act, ligne in zip(e.activites, impact.lignes):
        f = ref.facteurs[act.facteur]
        lignes.append({
            "poste": ligne.libelle,
            "quantite": ligne.quantite, "unite": ligne.unite,
            "facteur": {"libelle": f.libelle, "kgco2e_par_unite": {"bas": f.bas, "central": f.valeur, "haut": f.haut},
                        "statut": f.statut, "note": f.note, "source": ctx.noter_source_referentiel(f.source)},
            "hypotheses": [{"libelle": ref.parametres[p].libelle, "valeur": ref.parametres[p].valeur,
                            "bas": ref.parametres[p].bas, "haut": ref.parametres[p].haut,
                            "unite": ref.parametres[p].unite, "statut": ref.parametres[p].statut}
                           for p in act.parametres],
            "impact_kgco2e": ligne.impact.arrondie(2),
        })
    return {"etape": e.titre, "pratique_actuelle": e.pratique_actuelle, "total_kgco2e": impact.total.arrondie(1),
            "lignes": lignes,
            "methode": "Fourchette = scénario bas (toutes bornes basses) et scénario haut (toutes bornes hautes)."}


def _chercher_sources(ctx: ContexteOutils, requete_en_anglais: str, theme: str) -> dict:
    themes = None if theme in (None, "tous") else [theme]
    hits = load_index().search(requete_en_anglais, k=5, themes=themes)
    out = []
    for h in hits:
        d = h.to_dict(900)
        ctx.noter_source(h.chunk_id, h.citation, d["url"], "corpus", d["extrait"])
        out.append({"id": h.chunk_id, "citation": h.citation, "titre": h.title, "licence": d["licence"],
                    "extrait": d["extrait"]})
    return {"resultats": out, "note": "Aucun résultat : reformuler en anglais avec d'autres mots-clés." if not out else None}


def _preparer_fiche_action(ctx: ContexteOutils, alternatives_retenues: list[str], alternatives_a_discuter: list[str]) -> dict:
    ctx.calc.parcours(alternatives_retenues)  # valide les choix (conflits)
    q = urllib.parse.urlencode([("retenues", a) for a in alternatives_retenues]
                               + [("discuter", a) for a in alternatives_a_discuter])
    ctx.fiche_url = f"/api/fiche?{q}"
    return {"url": ctx.fiche_url, "actions": len(alternatives_retenues), "a_discuter": len(alternatives_a_discuter)}


_EXECUTEURS = {
    "calculer_impact": _calculer_impact,
    "chercher_alternatives": _chercher_alternatives,
    "expliquer_calcul": _expliquer_calcul,
    "chercher_sources": _chercher_sources,
    "preparer_fiche_action": _preparer_fiche_action,
}


def executer(ctx: ContexteOutils, nom: str, arguments: dict) -> tuple[str, bool]:
    """Exécute un outil. Renvoie (contenu JSON, est_une_erreur)."""
    fn = _EXECUTEURS.get(nom)
    if fn is None:
        return json.dumps({"erreur": f"outil inconnu : {nom}"}), True
    try:
        resultat = fn(ctx, **arguments)
    except ConflitAlternatives as exc:
        return json.dumps({"erreur": str(exc)}, ensure_ascii=False), True
    except (KeyError, TypeError, ValueError, FileNotFoundError) as exc:
        return json.dumps({"erreur": f"{type(exc).__name__} : {exc}"}, ensure_ascii=False), True
    ctx.noter_nombres(resultat)
    return json.dumps(resultat, ensure_ascii=False), False
