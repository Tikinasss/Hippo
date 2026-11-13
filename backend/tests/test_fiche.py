from hippo.action_plan import construire_fiche, rendre_html


def test_fiche_reprend_les_actions_et_leurs_sources():
    fiche = construire_fiche(["aivoc", "regroupement_consultations"], a_discuter=["kit_optimise"])
    assert [a["id"] for a in fiche["actions"]] == ["aivoc", "regroupement_consultations"]
    aivoc = fiche["actions"][0]
    assert aivoc["indicateur"]
    assert any("SFAR" in s for s in aivoc["sources"])
    assert fiche["a_discuter"][0]["titre"].startswith("Kit optimisé")
    assert fiche["impact"]["evite"]["central"] > 0


def test_html_sans_balise_non_remplacee_et_echappe():
    fiche = construire_fiche(["aivoc"], etablissement="CHU <test>")
    page = rendre_html(fiche)
    assert "{{" not in page
    assert "CHU &lt;test&gt;" in page
    assert "AIVOC" in page and "Enregistrer en PDF" in page


def test_fiche_vide():
    page = rendre_html(construire_fiche([]))
    assert "Aucune action retenue" in page
