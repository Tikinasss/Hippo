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
    monkeypatch.setattr(main, "_assistant", Assistant(client=faux, stockage=main.stockage(), calc_pour=main.calc_equipe))
    r = client.post("/api/assistant", json={"question": "Bonjour"})
    assert r.status_code == 200 and r.json()["statut"] == "ok"
    # la conversation est enregistrée : une nouvelle instance de l'assistant la retrouve
    cid = r.json()["conversation_id"]
    assert main.stockage().conversation(cid)["messages"][0]["role"] == "user"
    monkeypatch.setattr(main, "_assistant", Assistant(client=faux, stockage=main.stockage(), calc_pour=main.calc_equipe))
    r2 = client.post("/api/assistant", json={"question": "Le bloc", "conversation_id": cid})
    assert r2.json()["conversation_id"] == cid
    assert len(main.stockage().conversation(cid)["messages"]) == 4


# --- Équipes, décisions, valeurs locales ----------------------------------------------------

def test_equipe_par_defaut_et_creation():
    assert client.get("/api/equipes").json()[0]["id"] == "demo"
    r = client.post("/api/equipes", json={"id": "chu-lyon", "etablissement": "CHU de Lyon", "service": "Chirurgie"})
    assert r.status_code == 201
    assert client.post("/api/equipes", json={"id": "chu-lyon", "etablissement": "x", "service": "y"}).status_code == 409
    assert client.get("/api/parcours", params={"equipe": "inconnue"}).status_code == 404


def test_decisions_partagees_et_historisees():
    url = "/api/equipes/demo/decisions"
    r = client.put(f"{url}/aivoc", json={"statut": "retenue", "auteur": "Dr A"})
    assert r.status_code == 200 and r.json()["retenues"] == ["aivoc"]
    # bas débit modifie le même poste que l'AIVOC : refus
    assert client.put(f"{url}/bas_debit", json={"statut": "retenue", "auteur": "Dr B"}).status_code == 409
    client.put(f"{url}/kit_optimise", json={"statut": "a_discuter", "auteur": "Dr B", "commentaire": "staff du 3"})
    client.put(f"{url}/aivoc", json={"statut": "aucune", "auteur": "Dr A"})
    etat = client.get("/api/equipes/demo/etat").json()
    assert etat["retenues"] == [] and etat["a_discuter"] == ["kit_optimise"]
    hist = client.get(f"{url}/historique").json()
    assert [h["alternative"] for h in hist] == ["aivoc", "kit_optimise", "aivoc"]
    assert hist[1]["commentaire"] == "staff du 3" and hist[0]["titre"]
    assert client.put(f"{url}/inconnue", json={"statut": "retenue", "auteur": "x"}).status_code == 404


def test_valeurs_locales_remplacent_les_hypotheses():
    avant = client.post("/api/impact", json={}).json()
    url = "/api/equipes/demo/parametres"
    r = client.put(f"{url}/distance_km", json={"valeur": 45, "bas": 40, "haut": 50, "origine": "DIM 2025",
                                               "auteur": "Cadre"})
    assert r.status_code == 200
    d = next(p for p in r.json()["parametres"] if p["id"] == "distance_km")
    assert d["local"]["valeur"] == 45 and d["reference"]["valeur"] == 20
    apres = client.post("/api/impact", json={}).json()
    assert apres["avant"]["total"]["central"] > avant["avant"]["total"]["central"]
    assert apres["part_hypotheses"] < avant["part_hypotheses"]
    # une autre équipe garde l'hypothèse
    client.post("/api/equipes", json={"id": "autre", "etablissement": "CH", "service": "Chir"})
    autre = client.post("/api/impact", json={"equipe": "autre"}).json()
    assert autre["avant"]["total"] == avant["avant"]["total"]
    # validations
    assert client.put(f"{url}/distance_km", json={"valeur": 45, "bas": 50, "origine": "x", "auteur": "y"}).status_code == 422
    assert client.put(f"{url}/inconnu", json={"valeur": 1, "origine": "x", "auteur": "y"}).status_code == 404
    # retour à l'hypothèse, historique conservé
    r = client.delete(f"{url}/distance_km", params={"auteur": "Cadre"})
    assert next(p for p in r.json()["parametres"] if p["id"] == "distance_km")["local"] is None
    assert len(r.json()["historique"]) == 2
    assert client.post("/api/impact", json={}).json()["avant"]["total"] == avant["avant"]["total"]


def test_fiche_au_nom_de_l_equipe():
    client.post("/api/equipes", json={"id": "chu-nantes", "etablissement": "CHU de Nantes", "service": "UCA"})
    r = client.get("/api/fiche", params={"equipe": "chu-nantes"})
    assert "CHU de Nantes" in r.text
