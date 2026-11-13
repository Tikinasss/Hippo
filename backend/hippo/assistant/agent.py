"""Boucle d'appel d'outils de l'assistant Hippo (API Claude, boucle manuelle).

La boucle est écrite à la main plutôt qu'avec le tool runner pour garder la main
sur les garde-fous : la réponse finale est contrôlée (citations, chiffres) et, en
cas d'échec, le modèle reçoit une consigne de correction ; au second échec la
réponse est bloquée.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field

import anthropic

from ..engine import Calculateur
from . import guardrails
from .prompts import SYSTEME
from .tools import ContexteOutils, definitions, executer

MODELE = os.environ.get("HIPPO_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("HIPPO_EFFORT", "medium")
MAX_TOURS = 10
MAX_CORRECTIONS = 1
BETAS = ["server-side-fallback-2026-07-01"]


@dataclass
class Conversation:
    id: str
    ctx: ContexteOutils
    messages: list[dict] = field(default_factory=list)


class Assistant:
    def __init__(self, client: anthropic.Anthropic | None = None, calc: Calculateur | None = None,
                 modele: str = MODELE, effort: str = EFFORT) -> None:
        self._client = client
        self.calc = calc or Calculateur()
        self.modele = modele
        self.effort = effort
        self.outils = definitions(self.calc)
        self.conversations: dict[str, Conversation] = {}

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def _appel(self, messages: list[dict]):
        return self.client.beta.messages.create(
            model=self.modele,
            max_tokens=16000,
            system=SYSTEME,
            tools=self.outils,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            cache_control={"type": "ephemeral"},
            betas=BETAS,
            fallbacks="default",
        )

    def conversation(self, conversation_id: str | None) -> Conversation:
        if conversation_id and conversation_id in self.conversations:
            return self.conversations[conversation_id]
        cid = conversation_id or uuid.uuid4().hex
        conv = Conversation(id=cid, ctx=ContexteOutils(calc=self.calc))
        self.conversations[cid] = conv
        return conv

    def repondre(self, question: str, conversation_id: str | None = None, retenues: list[str] | None = None) -> dict:
        conv = self.conversation(conversation_id)
        contenu = []
        if retenues is not None:
            contenu.append({"type": "text", "text": f"[Contexte de l'écran] Alternatives déjà retenues par l'équipe : "
                                                     f"{', '.join(retenues) or 'aucune'}."})
        contenu.append({"type": "text", "text": question})
        conv.messages.append({"role": "user", "content": contenu})

        trace: list[dict] = []
        corrections = 0
        for _ in range(MAX_TOURS):
            reponse = self._appel(conv.messages)
            conv.messages.append({"role": "assistant", "content": reponse.content})

            if reponse.stop_reason == "pause_turn":
                continue
            if reponse.stop_reason == "tool_use":
                resultats = []
                for bloc in reponse.content:
                    if bloc.type != "tool_use":
                        continue
                    sortie, erreur = executer(conv.ctx, bloc.name, dict(bloc.input))
                    trace.append({"outil": bloc.name, "arguments": dict(bloc.input), "erreur": erreur})
                    resultats.append({"type": "tool_result", "tool_use_id": bloc.id, "content": sortie,
                                      **({"is_error": True} if erreur else {})})
                conv.messages.append({"role": "user", "content": resultats})
                continue
            if reponse.stop_reason == "refusal":
                return self._resultat(conv, "refus", "Cette demande ne peut pas être traitée par l'assistant.", trace)
            if reponse.stop_reason == "max_tokens":
                return self._resultat(conv, "tronquee", "La réponse a été interrompue (longueur maximale). "
                                                        "Reformulez la question de façon plus ciblée.", trace)

            texte = "".join(b.text for b in reponse.content if b.type == "text").strip()
            verif = guardrails.verifier(texte, set(conv.ctx.sources_vues), conv.ctx.nombres)
            if verif.ok:
                texte_num, refs = guardrails.numeroter(texte, conv.ctx.sources_vues)
                return self._resultat(conv, "ok", texte_num, trace, refs, verif)
            if corrections < MAX_CORRECTIONS:
                corrections += 1
                trace.append({"controle": verif.to_dict()})
                conv.messages.append({"role": "user", "content": [{"type": "text", "text": verif.consigne_correction()}]})
                continue
            return self._resultat(
                conv, "bloquee",
                "Je ne peux pas afficher de réponse sourcée à cette question. Reformulez-la, ou consultez "
                "directement la bibliothèque d'alternatives et ses références.",
                trace, verification=verif,
            )
        return self._resultat(conv, "interrompue", "L'assistant n'a pas abouti dans le nombre d'étapes autorisé.", trace)

    @staticmethod
    def _resultat(conv: Conversation, statut: str, texte: str, trace: list[dict],
                  references: list[dict] | None = None, verification: guardrails.Verification | None = None) -> dict:
        return {
            "conversation_id": conv.id,
            "statut": statut,
            "reponse": texte,
            "references": references or [],
            "fiche_url": conv.ctx.fiche_url,
            "outils": trace,
            "verification": verification.to_dict() if verification else None,
        }
