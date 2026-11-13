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
