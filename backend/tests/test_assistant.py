import json
from types import SimpleNamespace as NS

import pytest

from hippo import config
from hippo.assistant import Assistant
from hippo.assistant.guardrails import numeroter, verifier
from hippo.assistant.tools import ContexteOutils, definitions, executer
from hippo.engine import Calculateur


# --- Garde-fous ------------------------------------------------------------------

def test_citation_inconnue_et_chiffre_invente_detectes():
    v = verifier("Le bloc pèse 99 kgCO2e [S:inventee].", {"sfar2023_ag"}, {27.2})
    assert v.citations_inconnues == ["inventee"]
    assert v.chiffres_non_traces == ["99 kgCO2e"]
    assert not v.ok


def test_chiffre_arrondi_et_pourcentage_acceptes():
    v = verifier("Le bloc représente 31 % du total, soit 27 kgCO₂e [S:rizan2023].", {"rizan2023"}, {27.2, 0.306})
    assert v.ok, v.to_dict()


def test_reponse_substantielle_sans_citation_bloquee():
    assert verifier("L'AIVOC est recommandée par la SFAR.", set(), set()).sans_source
    assert verifier("Pouvez-vous préciser l'étape qui vous intéresse ?", set(), set()).ok


def test_numerotation_des_references():
    vues = {"a": {"id": "a", "citation": "A"}, "b": {"id": "b", "citation": "B"}}
    texte, refs = numeroter("X [S:a][S:a] puis Y [S:b] et Z [S:a].", vues)
    assert texte == "X [1] puis Y [2] et Z [1]."
    assert [r["numero"] for r in refs] == [1, 2] and refs[1]["citation"] == "B"


# --- Outils --------------------------------------------------------------------------

@pytest.fixture
def ctx():
    return ContexteOutils(calc=Calculateur())


def test_definitions_strictes(ctx):
    for d in definitions(ctx.calc):
        assert d["strict"] and d["input_schema"]["additionalProperties"] is False
        assert set(d["input_schema"]["required"]) == set(d["input_schema"]["properties"])


def test_calculer_impact_trace_sources_et_nombres(ctx):
    sortie, erreur = executer(ctx, "calculer_impact", {"alternatives_retenues": ["aivoc"]})
    assert not erreur
    data = json.loads(sortie)
    assert data["evite"]["central"] in ctx.nombres
    assert "ademe_base_carbone" in ctx.sources_vues


def test_conflit_renvoye_comme_erreur(ctx):
    sortie, erreur = executer(ctx, "calculer_impact", {"alternatives_retenues": ["aivoc", "bas_debit"]})
    assert erreur and "même poste" in json.loads(sortie)["erreur"]


def test_fiche_action_renvoie_un_lien(ctx):
    sortie, erreur = executer(ctx, "preparer_fiche_action",
                              {"alternatives_retenues": ["aivoc"], "alternatives_a_discuter": ["kit_optimise"]})
    assert not erreur and json.loads(sortie)["url"] == "/api/fiche?retenues=aivoc&discuter=kit_optimise"


@pytest.mark.skipif(not config.CHUNKS_PATH.exists(), reason="index RAG non construit")
def test_chercher_sources(ctx):
    sortie, _ = executer(ctx, "chercher_sources", {"requete_en_anglais": "local anaesthesia inguinal hernia", "theme": "tous"})
    res = json.loads(sortie)["resultats"]
    assert res and res[0]["id"] in ctx.sources_vues


# --- Boucle ----------------------------------------------------------------------------

class FauxClient:
    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.appels = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.appels.append({**kw, "messages": list(kw["messages"])})  # instantané : la liste continue d'évoluer
        return self.reponses.pop(0)


def outil(nom, args, id_="t1"):
    return NS(stop_reason="tool_use", content=[NS(type="tool_use", name=nom, input=args, id=id_)])


def texte(t):
    return NS(stop_reason="end_turn", content=[NS(type="text", text=t)])


def test_boucle_outil_puis_reponse_sourcee():
    calc = Calculateur()
    evite = calc.parcours(["aivoc"])["evite"]["central"]
    client = FauxClient([
        outil("calculer_impact", {"alternatives_retenues": ["aivoc"]}),
        texte(f"L'AIVOC éviterait {evite} kgCO2e par patient [S:drew2021]."),
    ])
    r = Assistant(client=client, calc=calc).repondre("Combien gagne-t-on avec l'AIVOC ?")
    assert r["statut"] == "ok", r
    assert r["reponse"].endswith("[1].") and r["references"][0]["id"] == "drew2021"
    assert r["outils"][0]["outil"] == "calculer_impact"
    # le résultat d'outil est renvoyé au modèle dans un message utilisateur
    assert client.appels[1]["messages"][-1]["content"][0]["type"] == "tool_result"
    assert client.appels[0]["model"] == "claude-opus-5-5"


def test_correction_puis_blocage():
    client = FauxClient([texte("Ça fait 999 kgCO2e."), texte("Toujours 999 kgCO2e.")])
    r = Assistant(client=client).repondre("Combien ?")
    assert r["statut"] == "bloquee"
    assert "Contrôle automatique" in client.appels[1]["messages"][-1]["content"][0]["text"]


def test_conversation_conserve_l_historique():
    client = FauxClient([texte("Bonjour, quelle étape vous intéresse ?"), texte("D'accord.")])
    a = Assistant(client=client)
    r1 = a.repondre("Bonjour", retenues=["aivoc"])
    r2 = a.repondre("Le bloc", conversation_id=r1["conversation_id"])
    assert r2["conversation_id"] == r1["conversation_id"]
    assert len(client.appels[1]["messages"]) == 3
    assert "aivoc" in client.appels[0]["messages"][0]["content"][0]["text"]


# --- Fournisseurs compatibles OpenAI (OpenRouter, Mistral, Ollama) ------------------------

from hippo.assistant.fournisseurs import ConfigurationManquante, FournisseurOpenAICompatible, creer


class FauxOpenAI:
    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.appels = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.appels.append({**kw, "messages": list(kw["messages"])})
        return self.reponses.pop(0)


def oa_outil(nom, arguments, id_="c1"):
    tc = NS(id=id_, type="function", function=NS(name=nom, arguments=arguments))
    return NS(choices=[NS(finish_reason="tool_calls", message=NS(content=None, tool_calls=[tc]))])


def oa_texte(t):
    return NS(choices=[NS(finish_reason="stop", message=NS(content=t, tool_calls=None))])


def test_openai_compatible_boucle_complete():
    calc = Calculateur()
    evite = calc.parcours(["aivoc"])["evite"]["central"]
    faux = FauxOpenAI([
        oa_outil("calculer_impact", '{"alternatives_retenues": ["aivoc"]}'),
        oa_texte(f"L'AIVOC éviterait {evite} kgCO2e [S:drew2021]."),
    ])
    f = FournisseurOpenAICompatible("openrouter", client=faux, modele="un/modele")
    r = Assistant(calc=calc, fournisseur=f).repondre("Gain de l'AIVOC ?")
    assert r["statut"] == "ok", r
    second = faux.appels[1]["messages"]
    assert second[0]["role"] == "system"
    assert second[-2]["tool_calls"][0]["function"]["name"] == "calculer_impact"
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "c1"
    assert faux.appels[0]["tools"][0]["type"] == "function"


def test_openai_compatible_arguments_invalides():
    faux = FauxOpenAI([oa_outil("calculer_impact", "{pas du json"), oa_texte("Pouvez-vous préciser ?")])
    f = FournisseurOpenAICompatible("ollama", client=faux)
    r = Assistant(fournisseur=f).repondre("?")
    assert r["outils"][0]["erreur"] is True
    assert "invalides" in faux.appels[1]["messages"][-1]["content"]


def test_choix_du_fournisseur(monkeypatch):
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY", "MISTRAL_API_KEY",
              "HIPPO_LLM_PROVIDER", "HIPPO_MODEL", "HIPPO_LLM_API_KEY", "HIPPO_LLM_BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ConfigurationManquante):
        creer()
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    g = creer()
    assert g.nom == "gemini" and "generativelanguage" in g._base_url
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("MISTRAL_API_KEY", "x")
    f = creer()
    assert f.nom == "mistral" and f.modele == "mistral-large-latest"
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    with pytest.raises(ConfigurationManquante, match="HIPPO_MODEL"):
        creer("openrouter")
    monkeypatch.setenv("HIPPO_MODEL", "fournisseur/modele")
    assert creer().nom == "openrouter"
