import html
import re

import pymupdf as fitz

from scraper import Chapter, WorkData

_CHAPTER_RE = re.compile(
    r"^(chapter|cap[ií]tulo|cap\.?)\s+[ivxlcdm\d]+\b",
    re.IGNORECASE,
)


def _clean_paragraph(text: str) -> str:
    return " ".join(line.strip() for line in text.splitlines() if line.strip())


def extract_pdf(pdf_bytes: bytes, title: str | None = None, author: str | None = None) -> WorkData:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise ValueError(f"No se pudo abrir el PDF: {e}") from e

    if doc.page_count == 0:
        raise ValueError("El PDF no tiene páginas.")

    meta = doc.metadata or {}
    final_title = (title or "").strip() or (meta.get("title") or "").strip() or "Sin título"
    final_author = (author or "").strip() or (meta.get("author") or "").strip() or "Desconocido/a"

    chapters: list[Chapter] = []
    current_title = final_title
    current_paras: list[str] = []

    def flush():
        if current_paras:
            body = "\n".join(f"<p>{html.escape(p)}</p>" for p in current_paras)
            chapters.append(Chapter(title=current_title, html=body))

    for page in doc:
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (round(b[1]), b[0]))
        for b in blocks:
            text = _clean_paragraph(b[4])
            if not text:
                continue
            if len(text) < 80 and _CHAPTER_RE.match(text):
                flush()
                current_title = text
                current_paras = []
                continue
            current_paras.append(text)

    flush()

    if not chapters:
        raise ValueError("No se encontró texto en el PDF (¿es un PDF escaneado sin OCR?).")

    return WorkData(
        title=final_title,
        author=final_author,
        language="es",
        summary="",
        chapters=chapters,
    )
