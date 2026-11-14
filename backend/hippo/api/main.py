"""API HTTP d'Hippo (FastAPI).

    uvicorn hippo.api.main:app --reload --port 8000

Chaque équipe (établissement + service) a ses propres valeurs locales (distances,
énergie…), ses décisions et ses conversations. Sans paramètre `equipe`, c'est
l'équipe par défaut (« demo ») qui est utilisée.
"""
from __future__ import annotations

import os

import anthropic
import openai
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ValidationError

from ..action_plan import construire_fiche, rendre_html
from ..assistant import Assistant
from ..assistant.fournisseurs import ConfigurationManquante, nom_par_defaut
from ..engine import Calculateur, ConflitAlternatives, referentiel
from ..rag import load_index
from ..rag.recherche import moteur_recherche
from ..store import EQUIPE_DEFAUT, Decision, Equipe, StatutDecision, Stockage, ValeurLocale, creer_stockage

app = FastAPI(title="Hippo API", version="0.2.0",
              description="Écoconception des parcours de soins : calcul, alternatives, sources, décisions et assistant.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("HIPPO_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAUT = EQUIPE_DEFAUT.id
_stockage: Stockage | None = None
_assistant: Assistant | None = None


def stockage() -> Stockage:
    global _stockage
    if _stockage is None:
        _stockage = creer_stockage()
    return _stockage


def calc_equipe(equipe_id: str) -> Calculateur:
    """Calculateur avec les valeurs locales de l'équipe à la place des hypothèses."""
    return Calculateur(referentiel().avec_valeurs_locales(stockage().valeurs_locales(equipe_id)))


def assistant() -> Assistant:
    global _assistant
    if _assistant is None:
        _assistant = Assistant(calc=Calculateur(), stockage=stockage(), calc_pour=calc_equipe)
    return _assistant


def _equipe(equipe_id: str) -> Equipe:
    e = stockage().equipe(equipe_id)
    if e is None:
        raise HTTPException(404, f"équipe inconnue : {equipe_id}")
    return e


def _calcul(calc: Calculateur, retenues: list[str]) -> dict:
    try:
        return calc.parcours(retenues)
    except ConflitAlternatives as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


def _source(calc: Calculateur, sid: str) -> dict:
    return calc.ref.sources[sid].model_dump()


# --- État du service ----------------------------------------------------------------------


@app.get("/api/sante")
def sante() -> dict:
    d = {"ok": True, "stockage": stockage().nom_complet, "recherche": moteur_recherche().mode}
    try:
        f = assistant().fournisseur
        return {**d, "assistant_configure": True, "fournisseur": f.nom, "modele": f.modele}
    except ConfigurationManquante as exc:
        return {**d, "assistant_configure": False, "fournisseur": nom_par_defaut(), "detail": str(exc)}


# --- Lecture du parcours et calcul ----------------------------------------------------------


@app.get("/api/parcours")
def parcours(equipe: str = DEFAUT) -> dict:
    _equipe(equipe)
    calc = calc_equipe(equipe)
    p = calc.ref.parcours
    return {
        "id": p.id, "titre": p.titre, "description": p.description, "perimetre": p.perimetre,
        "parametres": [x.model_dump() for x in p.parametres],
        "etapes": [
            {"id": e.id, "ordre": e.ordre, "jour": e.jour, "titre": e.titre, "acteur": e.acteur,
             "pratique_actuelle": e.pratique_actuelle,
             "alternatives": [a.id for a in calc.ref.alternatives_de(e.id)]}
            for e in p.etapes
        ],
    }


class DemandeImpact(BaseModel):
    retenues: list[str] = Field(default_factory=list)
    equipe: str = DEFAUT


@app.post("/api/impact")
def impact(demande: DemandeImpact) -> dict:
    _equipe(demande.equipe)
    return _calcul(calc_equipe(demande.equipe), demande.retenues)


@app.get("/api/alternatives")
def alternatives(etape: str | None = None, equipe: str = DEFAUT) -> list[dict]:
    _equipe(equipe)
    calc = calc_equipe(equipe)
    alts = calc.ref.alternatives_de(etape) if etape else list(calc.ref.alternatives.values())
    return [
        {**a.model_dump(exclude={"remplace"}),
         "gain_kgco2e": calc.gain_alternative(a.id)["gain_kgco2e"],
         "sources": [_source(calc, s) for s in a.sources]}
        for a in alts
    ]


@app.get("/api/etapes/{etape_id}/calcul")
def detail_calcul(etape_id: str, equipe: str = DEFAUT) -> dict:
    _equipe(equipe)
    calc = calc_equipe(equipe)
    try:
        e = calc.ref.etape(etape_id)
    except StopIteration as exc:
        raise HTTPException(404, f"étape inconnue : {etape_id}") from exc
    i = calc.impact_etape(e)
    params = calc.ref.parametres
    utilises = sorted({p for a in e.activites for p in a.parametres})
    return {**i.to_dict(),
            "facteurs": {l.facteur: calc.ref.facteurs[l.facteur].model_dump() for l in i.lignes},
            "parametres": [params[p].model_dump() for p in utilises]}


@app.get("/api/sources")
def sources() -> list[dict]:
    return [s.model_dump() for s in referentiel().sources.values()]


@app.get("/api/corpus/recherche")
def recherche(q: str, theme: str | None = None, k: int = Query(5, ge=1, le=20)) -> list[dict]:
    try:
        load_index()
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    return [h.to_dict(600) for h in moteur_recherche().chercher(q, k=k, themes=[theme] if theme else None)]


# --- Équipes ----------------------------------------------------------------------------


@app.get("/api/equipes")
def lister_equipes() -> list[dict]:
    return [e.model_dump() for e in stockage().equipes()]


@app.post("/api/equipes", status_code=201)
def creer_equipe(e: Equipe) -> dict:
    if stockage().equipe(e.id):
        raise HTTPException(409, f"l'équipe {e.id} existe déjà")
    return stockage().creer_equipe(e).model_dump()


def _etat(equipe_id: str) -> dict:
    decisions = stockage().decisions(equipe_id)
    return {
        "equipe": _equipe(equipe_id).model_dump(),
        "retenues": [a for a, d in decisions.items() if d.statut == "retenue"],
        "a_discuter": [a for a, d in decisions.items() if d.statut == "a_discuter"],
        "decisions": [d.model_dump() for d in decisions.values()],
        "valeurs_locales": len(stockage().valeurs_locales(equipe_id)),
    }


@app.get("/api/equipes/{equipe_id}/etat")
def etat_equipe(equipe_id: str) -> dict:
    return _etat(equipe_id)


class DemandeDecision(BaseModel):
    statut: StatutDecision
    auteur: str = Field(..., min_length=1, max_length=120)
    commentaire: str | None = Field(None, max_length=1000)


@app.put("/api/equipes/{equipe_id}/decisions/{alternative}")
def decider(equipe_id: str, alternative: str, demande: DemandeDecision) -> dict:
    _equipe(equipe_id)
    calc = calc_equipe(equipe_id)
    if alternative not in calc.ref.alternatives:
        raise HTTPException(404, f"alternative inconnue : {alternative}")
    if demande.statut == "retenue":
        actuelles = [a for a, d in stockage().decisions(equipe_id).items() if d.statut == "retenue" and a != alternative]
        _calcul(calc, [*actuelles, alternative])  # 409 si deux alternatives modifient le même poste
    stockage().ajouter_decision(equipe_id, Decision(alternative=alternative, **demande.model_dump()))
    return _etat(equipe_id)


@app.get("/api/equipes/{equipe_id}/decisions/historique")
def historique_decisions(equipe_id: str) -> list[dict]:
    _equipe(equipe_id)
    titres = {a.id: a.titre for a in referentiel().alternatives.values()}
    return [{**d.model_dump(), "titre": titres.get(d.alternative, d.alternative)}
            for d in reversed(stockage().historique_decisions(equipe_id))]


# --- Valeurs locales (remplacent les hypothèses) ------------------------------------------


@app.get("/api/equipes/{equipe_id}/parametres")
def parametres_equipe(equipe_id: str) -> dict:
    _equipe(equipe_id)
    base = referentiel().parametres
    locales = {v.parametre: v for v in stockage().valeurs_locales(equipe_id)}
    libelles = {p.id: p.libelle for p in base.values()}
    return {
        "parametres": [
            {"id": p.id, "libelle": p.libelle, "unite": p.unite,
             "reference": p.model_dump(include={"valeur", "bas", "haut", "statut", "source", "note"}),
             "local": locales[p.id].model_dump(exclude={"actif"}) if p.id in locales else None}
            for p in base.values()
        ],
        "historique": [{**v.model_dump(), "libelle": libelles.get(v.parametre, v.parametre)}
                       for v in reversed(stockage().historique_valeurs(equipe_id))],
        "part_hypotheses": calc_equipe(equipe_id).parcours()["part_hypotheses"],
    }


class DemandeValeur(BaseModel):
    valeur: float
    bas: float | None = None
    haut: float | None = None
    origine: str = Field(..., min_length=1, max_length=500)
    auteur: str = Field(..., min_length=1, max_length=120)


@app.put("/api/equipes/{equipe_id}/parametres/{parametre}")
def saisir_valeur(equipe_id: str, parametre: str, demande: DemandeValeur) -> dict:
    _equipe(equipe_id)
    if parametre not in referentiel().parametres:
        raise HTTPException(404, f"paramètre inconnu : {parametre}")
    try:
        v = ValeurLocale(parametre=parametre, **demande.model_dump())
    except ValidationError as exc:
        raise HTTPException(422, "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())) from exc
    stockage().ajouter_valeur(equipe_id, v)
    return parametres_equipe(equipe_id)


@app.delete("/api/equipes/{equipe_id}/parametres/{parametre}")
def retirer_valeur(equipe_id: str, parametre: str, auteur: str = Query(..., min_length=1, max_length=120)) -> dict:
    """Revient à l'hypothèse du référentiel (l'historique garde la trace)."""
    _equipe(equipe_id)
    if parametre not in referentiel().parametres:
        raise HTTPException(404, f"paramètre inconnu : {parametre}")
    stockage().ajouter_valeur(equipe_id, ValeurLocale(parametre=parametre, auteur=auteur, actif=False))
    return parametres_equipe(equipe_id)


# --- Fiche action --------------------------------------------------------------------


@app.get("/api/fiche", response_class=HTMLResponse)
def fiche_html(retenues: list[str] = Query(default=[]), discuter: list[str] = Query(default=[]),
               equipe: str = DEFAUT, etablissement: str | None = None, service: str | None = None) -> str:
    e = _equipe(equipe)
    calc = calc_equipe(equipe)
    _calcul(calc, retenues)
    return rendre_html(construire_fiche(retenues, discuter, etablissement or e.etablissement, service or e.service,
                                        calc=calc))


@app.get("/api/fiche.json")
def fiche_json(retenues: list[str] = Query(default=[]), discuter: list[str] = Query(default=[]),
               equipe: str = DEFAUT) -> dict:
    e = _equipe(equipe)
    calc = calc_equipe(equipe)
    _calcul(calc, retenues)
    return construire_fiche(retenues, discuter, e.etablissement, e.service, calc=calc)


# --- Assistant -----------------------------------------------------------------------


class Question(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None
    retenues: list[str] | None = None
    equipe: str = DEFAUT


@app.post("/api/assistant")
def poser_question(q: Question) -> dict:
    _equipe(q.equipe)
    try:
        return assistant().repondre(q.question, q.conversation_id, q.retenues, equipe=q.equipe)
    except ConfigurationManquante as exc:
        raise HTTPException(503, str(exc)) from exc
    except (anthropic.AuthenticationError, openai.AuthenticationError) as exc:
        raise HTTPException(503, "Clé d'API du modèle invalide.") from exc
    except (anthropic.RateLimitError, openai.RateLimitError) as exc:
        raise HTTPException(429, "Limite de requêtes atteinte, réessayez dans un instant.") from exc
    except (anthropic.APITimeoutError, openai.APITimeoutError) as exc:
        raise HTTPException(504, "Le modèle met trop de temps à répondre. Réessayez, ou changez de modèle.") from exc
    except (anthropic.APIConnectionError, openai.APIConnectionError) as exc:
        raise HTTPException(503, "Service du modèle injoignable.") from exc
    except (anthropic.APIStatusError, openai.APIStatusError) as exc:
        if exc.status_code in (503, 529):
            raise HTTPException(503, "Le modèle est surchargé chez le fournisseur. Réessayez dans un instant, "
                                     "ou changez de modèle (HIPPO_MODEL).") from exc
        if exc.status_code == 404:
            raise HTTPException(502, "Modèle introuvable chez le fournisseur : vérifiez HIPPO_MODEL.") from exc
        raise HTTPException(502, f"Erreur du service du modèle ({exc.status_code}).") from exc
