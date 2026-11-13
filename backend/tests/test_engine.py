import json
import shutil
from pathlib import Path

import pytest

from hippo import config
from hippo.engine import Calculateur, ConflitAlternatives, DonneesInvalides, charger


@pytest.fixture(scope="module")
def calc() -> Calculateur:
    return Calculateur(charger())


def test_donnees_coherentes():
    ref = charger()
    assert len(ref.parcours.etapes) == 8
    assert all(a.sources for a in ref.alternatives.values()), "pas de suggestion sans source"


def test_ligne_calcule_quantite_fois_facteur(calc):
    etape = calc.ref.etape("consultation_chirurgicale")
    ligne = calc.impact_etape(etape).lignes[0]
    # 2 trajets × 20 km × 0,256 kgCO2e/km
    assert ligne.impact.central == pytest.approx(2 * 20 * 0.256)
    # scénario bas : 2 × 10 km × 0,102 ; haut : 2 × 40 km × 0,410
    assert ligne.impact.bas == pytest.approx(2 * 10 * 0.102)
    assert ligne.impact.haut == pytest.approx(2 * 40 * 0.410)


def test_fourchettes_ordonnees(calc):
    r = calc.parcours()
    for e in r["avant"]["etapes"]:
        i = e["impact_kgco2e"]
        assert i["bas"] <= i["central"] <= i["haut"]


def test_sans_alternative_aucun_gain(calc):
    r = calc.parcours()
    assert r["evite"]["central"] == 0
    assert r["avant"]["total"] == r["apres"]["total"]


def test_regroupement_supprime_le_second_trajet(calc):
    g = calc.gain_alternative("regroupement_consultations")
    assert g["apres_kgco2e"]["central"] == 0
    assert g["gain_kgco2e"]["central"] == pytest.approx(10.2, abs=0.1)


def test_aivoc_reduit_le_bloc(calc):
    g = calc.gain_alternative("aivoc")
    # (14,5 − 0,5) kgCO2e/h × 1 h
    assert g["gain_kgco2e"]["central"] == pytest.approx(14.0, abs=0.1)
    assert g["gain_kgco2e"]["bas"] > 0


def test_deux_options_sur_le_meme_poste_sont_refusees(calc):
    with pytest.raises(ConflitAlternatives, match="anesthesie"):
        calc.parcours(["aivoc", "bas_debit"])


def test_options_sur_des_postes_differents_se_cumulent(calc):
    seul = calc.gain_alternative("aivoc")["gain_kgco2e"]["central"]
    kit = calc.gain_alternative("kit_optimise")["gain_kgco2e"]["central"]
    r = calc.parcours(["aivoc", "kit_optimise"])
    assert r["evite"]["central"] == pytest.approx(seul + kit, abs=0.11)


def test_extrapolation_annuelle(calc):
    r = calc.parcours(["aivoc"])
    n = r["annuel"]["interventions"]
    assert r["annuel"]["evite_tco2e"]["central"] == pytest.approx(r["evite"]["central"] * n / 1000, rel=0.01)


def test_alternative_inconnue(calc):
    with pytest.raises(KeyError):
        calc.parcours(["inexistante"])


def test_reference_cassee_detectee(tmp_path: Path):
    for f in config.DATA_DIR.glob("*.json"):
        shutil.copy(f, tmp_path / f.name)
    alts = json.loads((tmp_path / "alternatives.json").read_text(encoding="utf-8"))
    alts[0]["sources"] = ["source_inventee"]
    (tmp_path / "alternatives.json").write_text(json.dumps(alts), encoding="utf-8")
    with pytest.raises(DonneesInvalides, match="source_inventee"):
        charger(tmp_path)


def test_unite_incoherente_detectee(tmp_path: Path):
    for f in config.DATA_DIR.glob("*.json"):
        shutil.copy(f, tmp_path / f.name)
    parcours = json.loads((tmp_path / "parcours_hernie.json").read_text(encoding="utf-8"))
    parcours["etapes"][0]["activites"][0]["unite"] = "kWh"
    (tmp_path / "parcours_hernie.json").write_text(json.dumps(parcours), encoding="utf-8")
    with pytest.raises(DonneesInvalides, match="incompatible"):
        charger(tmp_path)
