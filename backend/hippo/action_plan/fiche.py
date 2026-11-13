"""Construction de la fiche action (données) et rendu HTML imprimable en PDF.

Le PDF est produit par le navigateur (« Imprimer > Enregistrer en PDF ») à partir
du HTML : aucune dépendance système à installer pour le prototype.
"""
from __future__ import annotations

import html
from datetime import date
from pathlib import Path

from ..engine import Calculateur

CRITERE_HAS = "Certification HAS des établissements de santé, transition écologique (critère 2.4-04 du référentiel 2027, numéro à confirmer)"
_TEMPLATE = Path(__file__).parent / "templates" / "fiche.html"


def construire_fiche(
    retenues: list[str],
    a_discuter: list[str] = (),
    etablissement: str = "CHU de démonstration",
    service: str = "Chirurgie ambulatoire",
    auteur: str | None = None,
    calc: Calculateur | None = None,
) -> dict:
    calc = calc or Calculateur()
    ref = calc.ref
    resultat = calc.parcours(retenues)

    actions = []
    for alt_id in resultat["retenues"]:
        alt = ref.alternatives[alt_id]
        actions.append(
            {
                "id": alt.id,
                "titre": alt.titre,
                "etape": ref.etape(alt.etape).titre,
                "statut": alt.statut,
                "gain_kgco2e": calc.gain_alternative(alt.id)["gain_kgco2e"],
                "securite": alt.securite,
                "conditions": alt.conditions,
                "vigilance": alt.vigilance,
                "indicateur": alt.indicateur,
                "sources": [ref.sources[s].citation for s in alt.sources],
            }
        )
    discussion = [
        {"titre": ref.alternatives[a].titre, "etape": ref.etape(ref.alternatives[a].etape).titre,
         "niveau_preuve": ref.alternatives[a].niveau_preuve}
        for a in a_discuter if a in ref.alternatives and a not in resultat["retenues"]
    ]
    hypotheses = [
        {"libelle": p.libelle, "valeur": p.valeur, "unite": p.unite}
        for p in ref.parcours.parametres if p.statut == "hypothese"
    ]
    sources_ids = sorted({s for a in resultat["retenues"] for s in ref.alternatives[a].sources}
                         | {f.source for f in ref.facteurs.values()})
    return {
        "titre": f"Fiche action – {resultat['parcours']['titre']}",
        "critere": CRITERE_HAS,
        "etablissement": etablissement,
        "service": service,
        "auteur": auteur,
        "date": date.today().isoformat(),
        "parcours": resultat["parcours"],
        "impact": {
            "avant": resultat["avant"]["total"],
            "apres": resultat["apres"]["total"],
            "evite": resultat["evite"],
            "reduction_pct": resultat["reduction_pct"],
            "annuel": resultat["annuel"],
        },
        "actions": actions,
        "a_discuter": discussion,
        "hypotheses": hypotheses,
        "part_hypotheses": resultat["part_hypotheses"],
        "sources": [ref.sources[s].citation for s in sources_ids],
    }


def _e(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def _f(fourchette: dict, unite: str = "kgCO₂e") -> str:
    return f"{fourchette['central']:g} {unite} <span class='range'>({fourchette['bas']:g} – {fourchette['haut']:g})</span>"


def rendre_html(fiche: dict) -> str:
    imp = fiche["impact"]
    lignes = "".join(
        f"<tr><td><strong>{_e(a['titre'])}</strong><br><span class='muted'>{_e(a['etape'])}</span></td>"
        f"<td>{'Validée' if a['statut'] == 'validee' else 'À discuter'}<br><span class='muted'>Sécurité {'équivalente' if a['securite'] == 'equivalente' else 'à évaluer'}</span></td>"
        f"<td class='num'>−{_f(a['gain_kgco2e'])}</td>"
        f"<td>{_e(a['indicateur'])}</td>"
        f"<td class='blank'></td><td class='blank'></td></tr>"
        f"<tr class='sub'><td colspan='6'><strong>Conditions :</strong> {_e(a['conditions'])}"
        + (f" · <strong>Vigilance :</strong> {_e('; '.join(a['vigilance']))}" if a["vigilance"] else "")
        + f"<br><strong>Sources :</strong> {_e(' ; '.join(a['sources']))}</td></tr>"
        for a in fiche["actions"]
    ) or "<tr><td colspan='6' class='muted'>Aucune action retenue pour l'instant.</td></tr>"
    discussion = "".join(
        f"<li><strong>{_e(d['titre'])}</strong> ({_e(d['etape'])}) — {_e(d['niveau_preuve'])}</li>" for d in fiche["a_discuter"]
    )
    hypotheses = "".join(f"<li>{_e(h['libelle'])} : {h['valeur']:g} {_e(h['unite'])}</li>" for h in fiche["hypotheses"])
    sources = "".join(f"<li>{_e(s)}</li>" for s in fiche["sources"])
    an = imp["annuel"]

    contenu = {
        "titre": _e(fiche["titre"]),
        "critere": _e(fiche["critere"]),
        "etablissement": _e(fiche["etablissement"]),
        "service": _e(fiche["service"]),
        "date": _e(fiche["date"]),
        "auteur": _e(fiche["auteur"] or "—"),
        "perimetre": _e(fiche["parcours"]["perimetre"]),
        "avant": _f(imp["avant"]),
        "apres": _f(imp["apres"]),
        "evite": _f(imp["evite"]),
        "reduction": f"{imp['reduction_pct']:g}",
        "annuel": f"{an['evite_tco2e']['central']:g} tCO₂e évitées par an pour {an['interventions']:g} interventions "
                  f"<span class='range'>({an['evite_tco2e']['bas']:g} – {an['evite_tco2e']['haut']:g})</span>",
        "actions": lignes,
        "discussion": f"<h2>À discuter en équipe</h2><ul>{discussion}</ul>" if discussion else "",
        "hypotheses": hypotheses,
        "part_hypotheses": f"{round(100 * fiche['part_hypotheses']):d}",
        "sources": sources,
    }
    page = _TEMPLATE.read_text(encoding="utf-8")
    for k, v in contenu.items():
        page = page.replace("{{" + k + "}}", v)
    return page
