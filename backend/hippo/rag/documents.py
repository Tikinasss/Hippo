"""Extraction du texte des documents du corpus (XML JATS d'Europe PMC et PDF).

Chaque document devient une liste de `Section` (titre + texte + page éventuelle),
qui garde assez de structure pour citer précisément la source.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

_WS = re.compile(r"\s+")


def clean(text: str) -> str:
    return _WS.sub(" ", text).strip()


@dataclass
class Section:
    heading: str
    text: str
    page: int | None = None


@dataclass
class Document:
    id: str
    title: str
    meta: dict
    sections: list[Section] = field(default_factory=list)


# --- XML JATS -----------------------------------------------------------------

_SKIP_TAGS = {"xref", "table-wrap", "fig", "sec", "title", "label", "inline-formula", "disp-formula"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _paragraph_text(el: ET.Element) -> str:
    """Texte d'un <p>, sans les sous-blocs (figures, tableaux) ni les appels de référence numériques."""
    parts: list[str] = [el.text or ""]
    for child in el:
        name = _local(child.tag)
        if name in {"table-wrap", "fig", "disp-formula"}:
            pass
        elif name == "xref":
            pass  # « [12] » n'apporte rien à la recherche
        else:
            parts.append("".join(child.itertext()))
        parts.append(child.tail or "")
    return clean("".join(parts))


def _table_text(tw: ET.Element) -> str:
    caption = tw.find(".//caption")
    lines = [clean("".join(caption.itertext()))] if caption is not None else []
    for row in tw.iter():
        if _local(row.tag) != "tr":
            continue
        cells = [clean("".join(c.itertext())) for c in row if _local(c.tag) in {"td", "th"}]
        if any(cells):
            lines.append(" | ".join(cells))
    foot = tw.find(".//table-wrap-foot")
    if foot is not None:
        lines.append(clean("".join(foot.itertext())))
    return "\n".join(line for line in lines if line)


def _walk_sec(sec: ET.Element, trail: list[str], out: list[Section]) -> None:
    title_el = sec.find("title")
    title = clean("".join(title_el.itertext())) if title_el is not None else ""
    path = [*trail, title] if title else trail
    heading = " > ".join(path) or "Texte"

    paragraphs: list[str] = []
    for child in sec:
        name = _local(child.tag)
        if name == "p":
            txt = _paragraph_text(child)
            if txt:
                paragraphs.append(txt)
            for tw in child.iter():
                if _local(tw.tag) == "table-wrap":
                    out.append(Section(heading=f"{heading} (tableau)", text=_table_text(tw)))
        elif name == "list":
            items = [clean("".join(li.itertext())) for li in child if _local(li.tag) == "list-item"]
            paragraphs.extend(f"- {i}" for i in items if i)
        elif name == "table-wrap":
            out.append(Section(heading=f"{heading} (tableau)", text=_table_text(child)))
        elif name == "sec":
            if paragraphs:
                out.append(Section(heading=heading, text="\n".join(paragraphs)))
                paragraphs = []
            _walk_sec(child, path, out)
    if paragraphs:
        out.append(Section(heading=heading, text="\n".join(paragraphs)))


def parse_jats(path: Path) -> list[Section]:
    root = ET.parse(path).getroot()
    sections: list[Section] = []

    for abstract in root.iter():
        if _local(abstract.tag) != "abstract":
            continue
        if abstract.get("abstract-type") in {"graphical", "teaser"}:
            continue
        text = clean(" ".join(abstract.itertext()))
        if text:
            sections.append(Section(heading="Résumé", text=text))
        break

    body = next((el for el in root.iter() if _local(el.tag) == "body"), None)
    if body is not None:
        loose: list[str] = []
        for child in body:
            name = _local(child.tag)
            if name == "sec":
                _walk_sec(child, [], sections)
            elif name == "p":
                txt = _paragraph_text(child)
                if txt:
                    loose.append(txt)
            elif name == "table-wrap":
                sections.append(Section(heading="Tableau", text=_table_text(child)))
        if loose:
            sections.insert(1 if sections else 0, Section(heading="Texte", text="\n".join(loose)))

    # Tableaux placés en annexe (<floats-group>) dans certains articles
    for fg in root.iter():
        if _local(fg.tag) == "floats-group":
            for tw in fg.iter():
                if _local(tw.tag) == "table-wrap":
                    sections.append(Section(heading="Tableau", text=_table_text(tw)))

    return [s for s in sections if s.text]


# --- PDF ------------------------------------------------------------------------


def parse_pdf(path: Path) -> list[Section]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    sections = []
    for i, page in enumerate(reader.pages, start=1):
        text = clean(page.extract_text() or "")
        if text:
            sections.append(Section(heading=f"Page {i}", text=text, page=i))
    return sections


# --- Manifest -------------------------------------------------------------------


def load_document(entry: dict, corpus_dir: Path) -> Document | None:
    """Charge un document décrit par une entrée du manifest, ou None s'il est absent."""
    if entry.get("status") != "ok":
        return None
    path = corpus_dir / entry["file"]
    if not path.exists():
        return None
    if path.suffix == ".xml":
        sections = parse_jats(path)
    elif path.suffix == ".pdf":
        sections = parse_pdf(path)
    else:
        return None
    meta = {k: entry.get(k) for k in ("authors", "journal", "year", "doi", "url", "license", "reuse", "theme", "source")}
    return Document(id=entry["id"], title=entry.get("title") or entry["id"], meta=meta, sections=sections)
