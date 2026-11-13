"""Fournisseurs de modèles de langage : Claude (SDK Anthropic) ou toute API compatible OpenAI
(OpenRouter, Mistral, Ollama en local…).

La boucle de l'assistant ne connaît que l'interface commune ci-dessous ; les outils,
le prompt et les garde-fous sont identiques quel que soit le fournisseur.

Choix par variables d'environnement :
    HIPPO_LLM_PROVIDER  anthropic | openrouter | mistral | gemini | ollama | openai_compatible
                        (défaut : détecté d'après la clé présente)
    HIPPO_MODEL         identifiant du modèle chez ce fournisseur
    HIPPO_LLM_BASE_URL  URL de base, pour openai_compatible (ou pour surcharger un préréglage)
    HIPPO_LLM_API_KEY   clé, pour openai_compatible (sinon la variable propre au fournisseur)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Protocol

from .. import config  # noqa: F401  (charge backend/.env avant de lire les variables)


class ConfigurationManquante(RuntimeError):
    """Aucune clé ou aucun modèle configuré pour le fournisseur choisi."""


@dataclass
class AppelOutil:
    id: str
    nom: str
    arguments: dict | None  # None : arguments illisibles (JSON invalide)
    brut: str = ""


@dataclass
class Tour:
    fin: str  # "outils" | "fin" | "pause" | "refus" | "longueur"
    texte: str
    appels: list[AppelOutil] = field(default_factory=list)
    message: object = None  # message assistant à rajouter tel quel à l'historique


class Fournisseur(Protocol):
    nom: str
    modele: str

    def appeler(self, systeme: str, outils: list[dict], messages: list) -> Tour: ...
    def message_utilisateur(self, textes: list[str]) -> list: ...
    def resultats_outils(self, resultats: list[tuple[str, str, bool]]) -> list: ...


# --- Claude (SDK Anthropic) ----------------------------------------------------------


class FournisseurAnthropic:
    nom = "anthropic"

    def __init__(self, client=None, modele: str | None = None, effort: str | None = None) -> None:
        self._client = client
        self.modele = modele or os.environ.get("HIPPO_MODEL", "claude-opus-5-5")
        self.effort = effort or os.environ.get("HIPPO_EFFORT", "medium")

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def appeler(self, systeme: str, outils: list[dict], messages: list) -> Tour:
        r = self.client.beta.messages.create(
            model=self.modele,
            max_tokens=16000,
            system=systeme,
            tools=outils,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            cache_control={"type": "ephemeral"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        fin = {"tool_use": "outils", "pause_turn": "pause", "refusal": "refus", "max_tokens": "longueur"}.get(
            r.stop_reason, "fin")
        appels = [AppelOutil(b.id, b.name, dict(b.input)) for b in r.content if b.type == "tool_use"]
        texte = "".join(b.text for b in r.content if b.type == "text").strip()
        # le contenu complet (réflexion comprise) est renvoyé tel quel au tour suivant
        return Tour(fin=fin, texte=texte, appels=appels, message={"role": "assistant", "content": r.content})

    def message_utilisateur(self, textes: list[str]) -> list:
        return [{"role": "user", "content": [{"type": "text", "text": t} for t in textes]}]

    def resultats_outils(self, resultats: list[tuple[str, str, bool]]) -> list:
        return [{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": i, "content": c, **({"is_error": True} if e else {})}
            for i, c, e in resultats
        ]}]


# --- API compatibles OpenAI (OpenRouter, Mistral, Ollama…) --------------------------------

PRESETS = {
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "cle": "OPENROUTER_API_KEY", "modele": None},
    "mistral": {"base_url": "https://api.mistral.ai/v1", "cle": "MISTRAL_API_KEY", "modele": "mistral-large-latest"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "cle": "GEMINI_API_KEY",
               "modele": "gemini-2.5-flash"},
    "ollama": {"base_url": "http://localhost:11434/v1", "cle": None, "modele": "llama3.1:8b"},
    "openai_compatible": {"base_url": None, "cle": "HIPPO_LLM_API_KEY", "modele": None},
}


class FournisseurOpenAICompatible:
    def __init__(self, nom: str = "openai_compatible", client=None, modele: str | None = None) -> None:
        if nom not in PRESETS:
            raise ConfigurationManquante(f"fournisseur inconnu : {nom}")
        preset = PRESETS[nom]
        self.nom = nom
        self.modele = modele or os.environ.get("HIPPO_MODEL") or preset["modele"]
        if not self.modele:
            raise ConfigurationManquante(
                f"Choisissez un modèle avec HIPPO_MODEL pour {nom} (un modèle qui gère l'appel d'outils)."
            )
        self._client = client
        self._base_url = os.environ.get("HIPPO_LLM_BASE_URL") or preset["base_url"]
        self._cle = os.environ.get("HIPPO_LLM_API_KEY") or (os.environ.get(preset["cle"]) if preset["cle"] else "ollama")
        if client is None and not self._base_url:
            raise ConfigurationManquante("Définissez HIPPO_LLM_BASE_URL pour openai_compatible.")
        if client is None and not self._cle:
            raise ConfigurationManquante(f"Clé absente : définissez {preset['cle']}.")

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(base_url=self._base_url, api_key=self._cle)
        return self._client

    @staticmethod
    def _outils(outils: list[dict]) -> list[dict]:
        # « strict » n'est pas accepté partout : les arguments sont de toute façon validés par l'exécuteur
        return [{"type": "function", "function": {"name": o["name"], "description": o["description"],
                                                  "parameters": o["input_schema"]}} for o in outils]

    def appeler(self, systeme: str, outils: list[dict], messages: list) -> Tour:
        r = self.client.chat.completions.create(
            model=self.modele,
            messages=[{"role": "system", "content": systeme}, *messages],
            tools=self._outils(outils),
            tool_choice="auto",
            max_tokens=4000,
        )
        choix = r.choices[0]
        msg = choix.message
        appels = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
                args = args if isinstance(args, dict) else None
            except json.JSONDecodeError:
                args = None
            appels.append(AppelOutil(tc.id, tc.function.name, args, tc.function.arguments or ""))
        fin = "outils" if appels else {"length": "longueur", "content_filter": "refus"}.get(choix.finish_reason, "fin")
        message = {"role": "assistant", "content": msg.content or ""}
        if appels:
            message["tool_calls"] = [
                {"id": a.id, "type": "function", "function": {"name": a.nom, "arguments": a.brut or "{}"}} for a in appels
            ]
        return Tour(fin=fin, texte=(msg.content or "").strip(), appels=appels, message=message)

    def message_utilisateur(self, textes: list[str]) -> list:
        return [{"role": "user", "content": "\n\n".join(textes)}]

    def resultats_outils(self, resultats: list[tuple[str, str, bool]]) -> list:
        return [{"role": "tool", "tool_call_id": i, "content": c} for i, c, _ in resultats]


# --- Choix --------------------------------------------------------------------------------


def nom_par_defaut() -> str:
    choix = os.environ.get("HIPPO_LLM_PROVIDER")
    if choix:
        return choix
    for nom, var in (("anthropic", "ANTHROPIC_API_KEY"), ("openrouter", "OPENROUTER_API_KEY"),
                     ("mistral", "MISTRAL_API_KEY"), ("gemini", "GEMINI_API_KEY")):
        if os.environ.get(var):
            return nom
    return "anthropic"


def creer(nom: str | None = None) -> Fournisseur:
    nom = nom or nom_par_defaut()
    if nom == "anthropic":
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise ConfigurationManquante(
                "Assistant non configuré : définissez ANTHROPIC_API_KEY, ou OPENROUTER_API_KEY / MISTRAL_API_KEY / GEMINI_API_KEY, "
                "ou HIPPO_LLM_PROVIDER=ollama pour un modèle local."
            )
        return FournisseurAnthropic()
    return FournisseurOpenAICompatible(nom)
