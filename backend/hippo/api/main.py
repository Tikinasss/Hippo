"""API HTTP d'Hippo (FastAPI).

    uvicorn hippo.api.main:app --reload --port 8000
"""
from __future__ import annotations

import os

import anthropic
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..action_plan import construire_fiche, rendre_html
import openai

from ..assistant import Assistant
from ..assistant.fournisseurs import ConfigurationManquante, nom_par_defaut
from ..engine import Calculateur, ConflitAlternatives
from ..rag import load_index

app = FastAPI(title="Hippo API", version="0.1.0",
              description="Écoconception des parcours de soins : calcul, alternatives, sources et assistant.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("HIPPO_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

calc = Calculateur()
_assistant: Assistant | None = None


def assistant() -> Assistant:
    global _assistant
    if _assistant is None:
        _assistant = Assistant(calc=calc)
    return _assistant


def _calcul(retenues: list[str]) -> dict:
    try:
        return calc.parcours(retenues)
    except ConflitAlternatives as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


def _source(sid: str) -> dict:
    s = calc.ref.sources[sid]
    return s.model_dump()


# --- Lecture ----------------------------------------------------------------------------


@app.get("/api/sante")
def sante() -> dict:
    try:
        f = assistant().fournisseur
        return {"ok": True, "assistant_configure": True, "fournisseur": f.nom, "modele": f.modele}
    except ConfigurationManquante as exc:
        return {"ok": True, "assistant_configure": False, "fournisseur": nom_par_defaut(), "detail": str(exc)}


@app.get("/api/parcours")
def parcours() -> dict:
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


@app.post("/api/impact")
def impact(demande: DemandeImpact) -> dict:
    return _calcul(demande.retenues)


@app.get("/api/alternatives")
def alternatives(etape: str | None = None) -> list[dict]:
    alts = calc.ref.alternatives_de(etape) if etape else list(calc.ref.alternatives.values())
    return [
        {**a.model_dump(exclude={"remplace"}),
         "gain_kgco2e": calc.gain_alternative(a.id)["gain_kgco2e"],
         "sources": [_source(s) for s in a.sources]}
        for a in alts
    ]


@app.get("/api/etapes/{etape_id}/calcul")
def detail_calcul(etape_id: str) -> dict:
    try:
        e = calc.ref.etape(etape_id)
    except StopIteration as exc:
        raise HTTPException(404, f"étape inconnue : {etape_id}") from exc
    i = calc.impact_etape(e)
    return {**i.to_dict(), "facteurs": {l.facteur: calc.ref.facteurs[l.facteur].model_dump() for l in i.lignes}}


@app.get("/api/sources")
def sources() -> list[dict]:
    return [s.model_dump() for s in calc.ref.sources.values()]


@app.get("/api/corpus/recherche")
def recherche(q: str, theme: str | None = None, k: int = Query(5, ge=1, le=20)) -> list[dict]:
    try:
        idx = load_index()
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    return [h.to_dict(600) for h in idx.search(q, k=k, themes=[theme] if theme else None)]


# --- Fiche action --------------------------------------------------------------------


@app.get("/api/fiche", response_class=HTMLResponse)
def fiche_html(retenues: list[str] = Query(default=[]), discuter: list[str] = Query(default=[]),
               etablissement: str = "CHU de démonstration", service: str = "Chirurgie ambulatoire") -> str:
    _calcul(retenues)
    return rendre_html(construire_fiche(retenues, discuter, etablissement, service, calc=calc))


@app.get("/api/fiche.json")
def fiche_json(retenues: list[str] = Query(default=[]), discuter: list[str] = Query(default=[])) -> dict:
    _calcul(retenues)
    return construire_fiche(retenues, discuter, calc=calc)


# --- Assistant -----------------------------------------------------------------------


class Question(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None
    retenues: list[str] | None = None


@app.post("/api/assistant")
def poser_question(q: Question) -> dict:
    try:
        return assistant().repondre(q.question, q.conversation_id, q.retenues)
    except ConfigurationManquante as exc:
        raise HTTPException(503, str(exc)) from exc
    except (anthropic.AuthenticationError, openai.AuthenticationError) as exc:
        raise HTTPException(503, "Clé d'API du modèle invalide.") from exc
    except (anthropic.RateLimitError, openai.RateLimitError) as exc:
        raise HTTPException(429, "Limite de requêtes atteinte, réessayez dans un instant.") from exc
    except (anthropic.APIConnectionError, openai.APIConnectionError) as exc:
        raise HTTPException(503, "Service du modèle injoignable.") from exc
    except (anthropic.APIStatusError, openai.APIStatusError) as exc:
        raise HTTPException(502, f"Erreur du service du modèle ({exc.status_code}).") from exc
