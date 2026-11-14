from pathlib import Path

from hippo.rag.bm25 import BM25, tokenize
from hippo.rag.chunking import chunk_document
from hippo.rag.documents import Document, Section, parse_jats
from hippo.rag.index import CorpusIndex

JATS = """<?xml version="1.0"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front><article-meta><abstract><p>Inguinal hernia repair has a carbon footprint of 11.7 kg CO2e.</p></abstract></article-meta></front>
  <body>
    <sec><title>Methods</title><p>We observed operations <xref>[3]</xref> at three sites.</p>
      <sec><title>Products</title><p>Gowns were single-use.</p>
        <table-wrap><caption><p>Table 1. Footprint</p></caption>
          <table><tr><th>Product</th><th>kg CO2e</th></tr><tr><td>Gown</td><td>2.1</td></tr></table>
        </table-wrap>
      </sec>
    </sec>
  </body>
</article>"""


def test_parse_jats_keeps_structure(tmp_path: Path):
    p = tmp_path / "a.xml"
    p.write_text(JATS, encoding="utf-8")
    sections = parse_jats(p)
    headings = [s.heading for s in sections]
    assert headings[0] == "Résumé"
    assert "Methods" in headings
    assert "Methods > Products" in headings
    table = next(s for s in sections if "tableau" in s.heading)
    assert "Gown | 2.1" in table.text
    methods = next(s for s in sections if s.heading == "Methods")
    assert "[3]" not in methods.text


def test_tokenize_strips_accents_stopwords_and_plurals():
    assert tokenize("Les anesthésies générales") == ["anesthesie", "generale"]
    assert tokenize("CO₂e emissions") == ["co2e", "emission"]
    assert tokenize("therapy therapies thérapies") == ["therapie"] * 3


def test_bm25_ranks_relevant_doc_first():
    docs = [tokenize(t) for t in ["sevoflurane volatile gas", "video consultation travel", "gown single use"]]
    top = BM25(docs).top(tokenize("video consultations"), k=3)
    assert top[0][0] == 1


def test_chunking_splits_long_sections_with_overlap():
    text = " ".join(f"Sentence number {i} talks about anaesthesia." for i in range(200))
    doc = Document(id="d", title="T", meta={}, sections=[Section(heading="H", text=text)])
    chunks = chunk_document(doc, max_chars=500, overlap=100)
    assert len(chunks) > 5
    assert all(len(c.text) <= 600 for c in chunks)
    assert chunks[0].id == "d#0" and chunks[1].id == "d#1"


def _chunk(i: int, doc: str, text: str, theme: str) -> dict:
    return {"id": f"{doc}#{i}", "doc_id": doc, "title": doc, "heading": "H", "text": text, "page": None,
            "meta": {"theme": theme, "authors": "Doe J, Roe K", "journal": "J", "year": "2024", "reuse": "integrer"}}


def test_index_filters_by_theme_and_limits_per_doc():
    idx = CorpusIndex([
        _chunk(0, "a", "telemedicine video follow up travel", "suivi"),
        _chunk(1, "a", "video consultation travel emissions", "suivi"),
        _chunk(2, "a", "video again travel", "suivi"),
        _chunk(0, "b", "video anaesthesia gas", "bloc"),
    ])
    hits = idx.search("video travel", k=5, per_doc=2)
    assert sum(h.doc_id == "a" for h in hits) == 2
    hits = idx.search("video", themes=["bloc"])
    assert [h.doc_id for h in hits] == ["b"]
    assert hits[0].citation.startswith("Doe J et al., J, 2024")


# --- Recherche hybride (embeddings simulés, sans réseau) --------------------------------------

import numpy as np

from hippo.rag.embeddings import DIM, VecteursFichier
from hippo.rag.recherche import MoteurRecherche


class FauxEmbeddeur:
    modele = "faux"

    def __init__(self, vecteurs):
        self.vecteurs = vecteurs

    def encoder_requete(self, texte):
        return self.vecteurs[texte]


def _vecteurs(chunks, matrice):
    return VecteursFichier([c["id"] for c in chunks], ["e"] * len(chunks), matrice, "faux",
                           {c["id"]: (c["meta"]["theme"], None) for c in chunks})


def test_hybride_trouve_par_le_sens_ce_que_les_mots_ratent():
    chunks = [_chunk(0, "a", "sevoflurane carbon footprint", "t"), _chunk(0, "b", "local anaesthesia hernia repair", "t"),
              _chunk(0, "c", "unrelated text about bicycles", "t")]
    base = np.eye(3, DIM, dtype=np.float32)
    q = base[1] * 0.9 + base[2] * 0.1
    question = "anesthésie locale de la hernie"  # aucun mot commun avec le passage b
    moteur = MoteurRecherche(CorpusIndex(chunks), FauxEmbeddeur({question: q / np.linalg.norm(q)}),
                             _vecteurs(chunks, base))
    assert moteur.mode == "hybride"
    assert moteur.chercher(question, k=1)[0].doc_id == "b"
    assert MoteurRecherche(CorpusIndex(chunks)).chercher(question, k=1) == []


def test_hybride_se_replie_sur_les_mots_cles_si_le_service_echoue():
    chunks = [_chunk(0, "a", "sevoflurane carbon footprint", "t")]

    class Panne:
        modele = "faux"

        def encoder_requete(self, texte):
            raise ConnectionError("hors ligne")

    moteur = MoteurRecherche(CorpusIndex(chunks), Panne(), _vecteurs(chunks, np.eye(1, DIM, dtype=np.float32)))
    assert moteur.chercher("sevoflurane", k=1)[0].doc_id == "a"


def test_vecteurs_fichier_aller_retour(tmp_path: Path):
    m = np.eye(2, DIM, dtype=np.float32)
    VecteursFichier(["x", "y"], ["e1", "e2"], m, "mod", {"x": ("t1", "integrer"), "y": ("t2", None)}).sauver(tmp_path / "v.npz")
    v = VecteursFichier.charger(tmp_path / "v.npz")
    assert v.ids == ["x", "y"] and v.modele == "mod"
    assert [i for i, _ in v.top(m[1], 2, themes=["t1"])] == ["x"]
