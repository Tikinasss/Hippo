import os

import pytest

from hippo.engine import Calculateur, referentiel
from hippo.store import Decision, Equipe, StockageFichier, ValeurLocale


def _remplir(s):
    s.creer_equipe(Equipe(id="e1", etablissement="CHU", service="Chir"))
    s.ajouter_valeur("e1", ValeurLocale(parametre="distance_km", valeur=30, origine="DIM", auteur="A"))
    s.ajouter_valeur("e1", ValeurLocale(parametre="energie_bloc_kwh", valeur=25, origine="ST", auteur="B"))
    s.ajouter_valeur("e1", ValeurLocale(parametre="energie_bloc_kwh", auteur="B", actif=False))
    s.ajouter_decision("e1", Decision(alternative="aivoc", statut="retenue", auteur="A"))
    s.ajouter_decision("e1", Decision(alternative="bilan_cible", statut="a_discuter", auteur="A"))
    s.ajouter_decision("e1", Decision(alternative="aivoc", statut="aucune", auteur="B"))
    s.enregistrer_conversation("c1", "e1", {"messages": [{"role": "user", "content": "x"}]})


def _verifier(s):
    assert [v.parametre for v in s.valeurs_locales("e1")] == ["distance_km"]
    assert len(s.historique_valeurs("e1")) == 3
    assert list(s.decisions("e1")) == ["bilan_cible"]
    assert len(s.historique_decisions("e1")) == 3
    assert s.conversation("c1")["messages"][0]["content"] == "x"
    assert s.conversation("c1")["equipe"] == "e1"
    assert s.equipe("e1").etablissement == "CHU" and s.equipe("zz") is None


def test_stockage_fichier_persiste(tmp_path):
    chemin = tmp_path / "etat.json"
    _remplir(StockageFichier(chemin))
    _verifier(StockageFichier(chemin))  # relu depuis le disque


def test_valeur_locale_validee():
    with pytest.raises(ValueError, match="origine"):
        ValeurLocale(parametre="distance_km", valeur=3, auteur="A")
    with pytest.raises(ValueError):
        ValeurLocale(parametre="distance_km", valeur=3, bas=4, origine="x", auteur="A")


def test_referentiel_avec_valeurs_locales():
    ref = referentiel()
    v = ValeurLocale(parametre="distance_km", valeur=40, origine="DIM", auteur="A")
    local = ref.avec_valeurs_locales([v])
    p = local.parametres["distance_km"]
    assert (p.valeur, p.bas, p.haut, p.statut, p.origine) == (40, 40, 40, "local", "DIM")
    assert ref.parametres["distance_km"].valeur == 20  # référentiel d'origine intact
    assert Calculateur(local).parcours()["part_hypotheses"] < Calculateur(ref).parcours()["part_hypotheses"]
    with pytest.raises(KeyError):
        ref.avec_valeurs_locales([ValeurLocale(parametre="zz", valeur=1, origine="x", auteur="A")])


URL_TEST = os.environ.get("HIPPO_TEST_DATABASE_URL")


@pytest.mark.skipif(not URL_TEST, reason="HIPPO_TEST_DATABASE_URL non défini (PostgreSQL de test)")
def test_stockage_postgres():
    from hippo.store.postgres import StockagePostgres

    s = StockagePostgres(URL_TEST)
    assert s.migrer() == []  # idempotent
    with s.pool.connection() as c:
        c.execute("DELETE FROM equipes WHERE id = 'e1'")
        c.execute("DELETE FROM conversations WHERE id = 'c1'")
    try:
        _remplir(s)
        _verifier(s)
    finally:
        with s.pool.connection() as c:
            c.execute("DELETE FROM equipes WHERE id = 'e1'")
        s.fermer()
