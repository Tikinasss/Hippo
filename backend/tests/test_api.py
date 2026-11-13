from types import SimpleNamespace as NS

from fastapi.testclient import TestClient

from hippo.api import main
from hippo.assistant import Assistant

client = TestClient(main.app)


def test_sante():
    assert client.get("/api/sante").json()["ok"] is True


def test_parcours_8_etapes():
    p = client.get("/api/parcours").json()
    assert len(p["etapes"]) == 8
    bloc = next(e for e in p["etapes"] if e["id"] == "bloc_operatoire")
    assert "aivoc" in bloc["alternatives"]


def test_impact_et_conflit():
    r = client.post("/api/impact", json={"retenues": ["aivoc"]})
    assert r.status_code == 200 and r.json()["evite"]["central"] > 0
    assert client.post("/api/impact", json={"retenues": ["aivoc", "bas_debit"]}).status_code == 409
    assert client.post("/api/impact", json={"retenues": ["nimporte"]}).status_code == 404


def test_alternatives_par_etape_avec_sources():
    alts = client.get("/api/alternatives", params={"etape": "bloc_operatoire"}).json()
    assert {a["id"] for a in alts} >= {"aivoc", "anesthesie_locale"}
    assert all(a["sources"] and "citation" in a["sources"][0] for a in alts)


def test_detail_calcul():
    d = client.get("/api/etapes/bloc_operatoire/calcul").json()
    assert "sevoflurane_2l_h" in d["facteurs"]
    assert client.get("/api/etapes/inconnue/calcul").status_code == 404


def test_fiche_html():
    r = client.get("/api/fiche", params=[("retenues", "aivoc"), ("discuter", "kit_optimise")])
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "AIVOC" in r.text


def test_assistant_avec_faux_client(monkeypatch):
    faux = NS(beta=NS(messages=NS(create=lambda **kw: NS(stop_reason="end_turn",
                                                           content=[NS(type="text", text="Quelle étape ?")]))))
    monkeypatch.setattr(main, "_assistant", Assistant(client=faux, calc=main.calc))
    r = client.post("/api/assistant", json={"question": "Bonjour"})
    assert r.status_code == 200 and r.json()["statut"] == "ok"
