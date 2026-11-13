"""Boucle d'appel d'outils de l'assistant Hippo, indépendante du fournisseur de modèle.

La boucle est écrite à la main pour garder la main sur les garde-fous : la réponse
finale est contrôlée (citations, chiffres) et, en cas d'échec, le modèle reçoit une
consigne de correction ; au second échec la réponse est bloquée.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from ..engine import Calculateur
from . import guardrails
from .fournisseurs import Fournisseur, FournisseurAnthropic, creer
from .prompts import SYSTEME
from .tools import ContexteOutils, definitions, executer

MAX_TOURS = 10
MAX_CORRECTIONS = 1
MAX_RECHERCHES = 3  # appels à chercher_sources par question
CONSIGNE_CONCLURE = ("[Contrôle automatique Hippo] Plus d'appel d'outil possible pour cette question : réponds "
                     "maintenant avec les résultats déjà obtenus, en citant leurs identifiants [S:id].")


@dataclass
class Conversation:
    id: str
    ctx: ContexteOutils
    messages: list = field(default_factory=list)


class Assistant:
    def __init__(self, client=None, calc: Calculateur | None = None, fournisseur: Fournisseur | None = None) -> None:
        # `client` : raccourci pour injecter un client Anthropic (tests)
        self._fournisseur = fournisseur or (FournisseurAnthropic(client=client) if client is not None else None)
        self.calc = calc or Calculateur()
        self.outils = definitions(self.calc)
        self.conversations: dict[str, Conversation] = {}

    @property
    def fournisseur(self) -> Fournisseur:
        if self._fournisseur is None:
            self._fournisseur = creer()  # lève ConfigurationManquante si rien n'est configuré
        return self._fournisseur

    def conversation(self, conversation_id: str | None) -> Conversation:
        if conversation_id and conversation_id in self.conversations:
            return self.conversations[conversation_id]
        cid = conversation_id or uuid.uuid4().hex
        conv = Conversation(id=cid, ctx=ContexteOutils(calc=self.calc))
        self.conversations[cid] = conv
        return conv

    def repondre(self, question: str, conversation_id: str | None = None, retenues: list[str] | None = None) -> dict:
        f = self.fournisseur
        conv = self.conversation(conversation_id)
        textes = []
        if retenues is not None:
            textes.append(f"[Contexte de l'écran] Alternatives déjà retenues par l'équipe : {', '.join(retenues) or 'aucune'}.")
        textes.append(question)
        conv.messages.extend(f.message_utilisateur(textes))

        trace: list[dict] = []
        corrections = 0
        recherches = 0
        for n_tour in range(MAX_TOURS):
            tour = f.appeler(SYSTEME, self.outils, conv.messages)
            conv.messages.append(tour.message)

            if tour.fin == "pause":
                continue
            if tour.fin == "outils":
                resultats = []
                for appel in tour.appels:
                    if appel.arguments is None:
                        sortie, erreur = json.dumps({"erreur": "arguments JSON invalides, réessayer"}), True
                    elif appel.nom == "chercher_sources" and recherches >= MAX_RECHERCHES:
                        sortie, erreur = json.dumps({"erreur": "Limite de recherches atteinte : réponds avec les "
                                                               "extraits déjà obtenus."}, ensure_ascii=False), True
                    else:
                        recherches += appel.nom == "chercher_sources"
                        sortie, erreur = executer(conv.ctx, appel.nom, appel.arguments)
                    trace.append({"outil": appel.nom, "arguments": appel.arguments, "erreur": erreur})
                    resultats.append((appel.id, sortie, erreur))
                # avant le dernier tour autorisé, on demande explicitement de conclure
                note = CONSIGNE_CONCLURE if n_tour >= MAX_TOURS - 3 else None
                conv.messages.extend(f.resultats_outils(resultats, note))
                continue
            if tour.fin == "refus":
                return self._resultat(conv, "refus", "Cette demande ne peut pas être traitée par l'assistant.", trace)
            if tour.fin == "longueur":
                return self._resultat(conv, "tronquee", "La réponse a été interrompue (longueur maximale). "
                                                        "Reformulez la question de façon plus ciblée.", trace)

            verif = guardrails.verifier(tour.texte, set(conv.ctx.sources_vues), conv.ctx.nombres)
            if verif.ok:
                texte_num, refs = guardrails.numeroter(tour.texte, conv.ctx.sources_vues)
                return self._resultat(conv, "ok", texte_num, trace, refs, verif)
            if corrections < MAX_CORRECTIONS:
                corrections += 1
                trace.append({"controle": verif.to_dict()})
                conv.messages.extend(f.message_utilisateur([verif.consigne_correction()]))
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
