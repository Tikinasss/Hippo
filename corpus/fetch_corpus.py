"""Télécharge le corpus RAG d'Hippo depuis Europe PMC et construit manifest.json.

Usage : python -I corpus/fetch_corpus.py

- Les articles viennent du sous-ensemble en accès ouvert d'Europe PMC (texte intégral XML JATS).
- Les documents web (HAS, rapports) sont listés dans WEB_DOCS ; ceux marqués manual=True
  bloquent les accès automatisés et doivent être téléchargés à la main dans corpus/raw/manual/.
- `reuse` indique ce que la licence permet :
    "integrer"  -> CC BY / CC0 / Licence Ouverte : peut entrer tel quel dans le corpus
    "non_commercial" -> CC BY-NC(-SA/-ND) : OK pour le hackathon (non commercial), à revoir avant tout usage commercial
    "citer" -> licence absente ou restrictive : citer avec lien, ne pas redistribuer
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
EPMC_DIR = RAW / "epmc"
WEB_DIR = RAW / "web"
MANUAL_DIR = RAW / "manual"
EPMC_REST = "https://www.ebi.ac.uk/europepmc/webservices/rest"

# PMCID -> thème du parcours
ARTICLES: dict[str, str] = {
    # Parcours clinique hernie
    "PMC5809582": "parcours_hernie",   # HerniaSurge, recommandations internationales 2018
    "PMC10588975": "parcours_hernie",  # HerniaSurge, mise à jour 2023
    # Bloc opératoire : produits, instruments, stérilisation
    "PMC10331364": "bloc_consommables",  # Rizan 2023, 5 opérations dont hernie inguinale
    "PMC10364739": "bloc_consommables",  # Rizan 2022, stérilisation des instruments
    "PMC12084675": "bloc_consommables",  # Optimisation des plateaux d'instruments 2025
    "PMC8274692": "bloc_consommables",   # Revue des ACV en chirurgie et anesthésie 2021
    "PMC11458728": "bloc_consommables",  # SAGES/EAES, revue de portée 2024
    "PMC10628494": "bloc_consommables",  # Checklist RCS green theatre 2023
    "PMC10364528": "bloc_consommables",  # Revue systématique mondiale, BJS 2023
    # Anesthésie
    "PMC11106536": "bloc_anesthesie",  # AIVOC vs inhalation : mortalité et morbidité, méta-analyse 2024
    "PMC8004846": "bloc_anesthesie",   # Gaz inhalés : rôle environnemental 2021
    "PMC9298028": "bloc_anesthesie",   # Consensus WFSA anesthésie durable 2022
    "PMC9543086": "bloc_anesthesie",   # Action guidance gaz inhalés 2022
    "PMC7421303": "bloc_anesthesie",   # BJA 2020, durabilité en anesthésie
    "PMC8415729": "bloc_anesthesie",   # Anesth Analg 2021, revue narrative
    # Préopératoire et biologie
    "PMC10335441": "preop_biologie",  # Coût environnemental des bilans sanguins inutiles 2023
    "PMC11698743": "preop_biologie",  # Aide à la décision préopératoire durable 2025
    "PMC9299213": "preop_biologie",   # High value care is low carbon care, MJA 2022
    # Suivi et téléconsultation
    "PMC9732751": "suivi_teleconsultation",  # Muschol 2022, RCT suivi vidéo
    "PMC4154849": "suivi_teleconsultation",  # Holmner 2014, empreinte de la télémédecine
    # Contexte système de santé
    "PMC7887664": "contexte",   # Empreinte carbone du NHS 2021
    "PMC11459334": "contexte",  # Stratégies de réduction, revue systématique BMJ 2024
}

WEB_DOCS = [
    {
        "id": "has_fiche_ecoconception",
        "title": "HAS — Fiche écoconception des soins",
        "url": "https://www.has-sante.fr/upload/docs/application/pdf/2025-09/dir12/fiche_ecoconception.pdf",
        "file": "has_fiche_ecoconception.pdf",
        "theme": "parcours_global",
        "license": "document public HAS",
        "reuse": "citer",
        "manual": False,
    },
    {
        "id": "imperial_susqi_hernie",
        "title": "Imperial College — SusQI : anesthésie locale ou générale pour la hernie",
        "url": "https://networks.sustainablehealthcare.org.uk/sites/default/files/resources/Imperial%20SusQI%20Project%20report%20.pdf",
        "file": "imperial_susqi_hernie.pdf",
        "theme": "bloc_anesthesie",
        "license": "rapport public, licence non précisée",
        "reuse": "citer",
        "manual": False,
    },
    {
        "id": "sfar_ecoconception_parcours",
        "title": "SFAR — Écoconception du parcours patient interventionnel chirurgical (2024)",
        "url": "https://sfar.org/download/ecoconception-du-parcours-patient-interventionnel-chirurgical/",
        "file": "sfar_ecoconception_parcours.pdf",
        "theme": "parcours_global",
        "license": "à vérifier",
        "reuse": "citer",
        "manual": True,
    },
    {
        "id": "sfar_reduction_impact_ag",
        "title": "SFAR — Réduction de l'impact environnemental de l'anesthésie générale",
        "url": "https://sfar.org/download/reduction-de-limpact-environnemental-de-lanesthesie-generale/",
        "file": "sfar_reduction_impact_ag.pdf",
        "theme": "bloc_anesthesie",
        "license": "à vérifier",
        "reuse": "citer",
        "manual": True,
    },
    {
        "id": "shift_project_sante",
        "title": "The Shift Project — Décarboner la santé, synthèse (2023)",
        "url": "https://theshiftproject.org/app/uploads/2025/01/180423-TSP-PTEF-Synthese-Sante_v2.pdf",
        "file": "shift_project_sante.pdf",
        "theme": "contexte",
        "license": "à vérifier",
        "reuse": "citer",
        "manual": True,
    },
    {
        "id": "ipcc_ar6_ch7_sm",
        "title": "GIEC AR6 GT1, chapitre 7, matériel supplémentaire (PRG des gaz)",
        "url": "https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_Chapter07_SM.pdf",
        "file": "ipcc_ar6_ch7_sm.pdf",
        "theme": "facteurs_emission",
        "license": "IPCC, reproduction non commerciale autorisée avec citation",
        "reuse": "citer",
        "manual": True,
    },
]


def reuse_from_license(lic: str | None) -> str:
    lic = (lic or "").lower().strip()
    if lic in {"cc by", "cc0", "cc by-sa"}:
        return "integrer"
    if lic.startswith("cc by-nc"):
        return "non_commercial"
    return "citer"


def get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "hippo-corpus-fetcher/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def epmc_metadata(pmcid: str) -> dict:
    q = urllib.parse.urlencode({"query": f"PMCID:{pmcid}", "resultType": "core", "format": "json"})
    res = json.loads(get(f"{EPMC_REST}/search?{q}"))["resultList"]["result"]
    if not res:
        raise ValueError(f"{pmcid} introuvable")
    a = res[0]
    journal = (a.get("journalInfo") or {}).get("journal", {})
    return {
        "title": a.get("title"),
        "authors": a.get("authorString"),
        "journal": journal.get("medlineAbbreviation") or journal.get("title"),
        "year": a.get("pubYear"),
        "doi": a.get("doi"),
        "license": a.get("license"),
    }


def main() -> None:
    for d in (EPMC_DIR, WEB_DIR, MANUAL_DIR):
        d.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []

    for pmcid, theme in ARTICLES.items():
        path = EPMC_DIR / f"{pmcid}.xml"
        entry = {"id": pmcid, "source": "europepmc", "theme": theme, "file": str(path.relative_to(ROOT))}
        try:
            entry |= epmc_metadata(pmcid)
            entry["reuse"] = reuse_from_license(entry.get("license"))
            entry["url"] = f"https://europepmc.org/article/PMC/{pmcid}"
            if not path.exists():
                path.write_bytes(get(f"{EPMC_REST}/{pmcid}/fullTextXML"))
                time.sleep(0.3)
            entry["status"] = "ok"
        except (urllib.error.URLError, ValueError, KeyError) as exc:
            entry["status"] = f"erreur : {exc}"
        print(f"{entry['status']:>6} | {pmcid} | {entry.get('license')} | {(entry.get('title') or '')[:80]}")
        manifest.append(entry)

    for doc in WEB_DOCS:
        target_dir = MANUAL_DIR if doc["manual"] else WEB_DIR
        path = target_dir / doc["file"]
        entry = {k: v for k, v in doc.items() if k not in {"file", "manual"}}
        entry |= {"source": "web", "file": str(path.relative_to(ROOT))}
        if path.exists():
            entry["status"] = "ok"
        elif doc["manual"]:
            entry["status"] = "a_telecharger_manuellement"
        else:
            try:
                path.write_bytes(get(doc["url"]))
                entry["status"] = "ok"
            except urllib.error.URLError as exc:
                entry["status"] = f"erreur : {exc}"
        print(f"{entry['status']:>6} | {doc['id']}")
        manifest.append(entry)

    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for e in manifest if e["status"] == "ok")
    print(f"\n{ok}/{len(manifest)} documents disponibles. Manifest : {ROOT / 'manifest.json'}")


if __name__ == "__main__":
    main()
