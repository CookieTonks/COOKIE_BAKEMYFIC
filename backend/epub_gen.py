import io
import os
import posixpath
import re
import tempfile
import zipfile
from xml.etree import ElementTree as ET

from ebooklib import epub

from scraper import WorkData

_OPF_NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
}

KINDLE_CSS = """
body {
    font-family: Georgia, serif;
    font-size: 1em;
    line-height: 1.7;
    margin: 0 5%;
    color: #1a1a1a;
}
h1 {
    font-size: 1.4em;
    font-weight: bold;
    margin: 1.5em 0 0.8em;
    text-align: center;
}
p {
    margin: 0 0 0.8em;
    text-indent: 1.2em;
}
p:first-of-type { text-indent: 0; }
hr {
    border: none;
    border-top: 1px solid #aaa;
    margin: 1.5em auto;
    width: 40%;
}
"""


def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip() or "fic"


def build_epub(work: WorkData, cover_bytes: bytes | None) -> bytes:
    book = epub.EpubBook()
    book.set_title(work.title)
    book.set_language(work.language or "en")
    book.add_author(work.author)

    if work.summary:
        book.add_metadata("DC", "description", work.summary)

    if cover_bytes:
        ext = "png" if cover_bytes[:8] == b"\x89PNG\r\n\x1a\n" else "jpg"
        book.set_cover(f"cover.{ext}", cover_bytes)

    style = epub.EpubItem(
        uid="style",
        file_name="style/main.css",
        media_type="text/css",
        content=KINDLE_CSS,
    )
    book.add_item(style)

    epub_chapters = []
    toc_links = []

    for i, ch in enumerate(work.chapters):
        title = ch.title or f"Capítulo {i + 1}"
        fname = f"chap_{i + 1:03d}.xhtml"
        epub_ch = epub.EpubHtml(title=title, file_name=fname, lang=work.language or "en")
        epub_ch.content = f"<h1>{title}</h1>\n{ch.html}"
        epub_ch.add_item(style)
        book.add_item(epub_ch)
        epub_chapters.append(epub_ch)
        toc_links.append(epub.Link(fname, title, f"chap_{i + 1}"))

    book.toc = toc_links
    book.spine = ["nav"] + epub_chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as f:
        tmp = f.name
    try:
        epub.write_epub(tmp, book)
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp)


def epub_filename(title: str) -> str:
    return _safe_filename(title) + ".epub"


def _find_opf_path(zf: zipfile.ZipFile) -> str:
    try:
        container = ET.fromstring(zf.read("META-INF/container.xml"))
    except KeyError as e:
        raise ValueError("El archivo no parece un EPUB válido (falta container.xml).") from e
    rootfile = container.find(".//c:rootfile", _OPF_NS)
    if rootfile is None or not rootfile.get("full-path"):
        raise ValueError("El archivo no parece un EPUB válido (container.xml sin rootfile).")
    return rootfile.get("full-path")


def _find_cover_image_path(zf: zipfile.ZipFile, opf_path: str) -> str:
    opf_dir = posixpath.dirname(opf_path)
    opf = ET.fromstring(zf.read(opf_path))
    manifest = opf.find("opf:manifest", _OPF_NS)
    metadata = opf.find("opf:metadata", _OPF_NS)

    href = None
    # EPUB3 convention: <item properties="cover-image" href="...">
    for item in manifest.findall("opf:item", _OPF_NS):
        if "cover-image" in (item.get("properties") or "").split():
            href = item.get("href")
            break

    # EPUB2 fallback: <meta name="cover" content="item-id"/> pointing at a manifest item
    if href is None and metadata is not None:
        cover_id = next(
            (m.get("content") for m in metadata.findall("opf:meta", _OPF_NS) if m.get("name") == "cover"),
            None,
        )
        if cover_id:
            href = next(
                (item.get("href") for item in manifest.findall("opf:item", _OPF_NS) if item.get("id") == cover_id),
                None,
            )

    if href is None:
        raise ValueError("Este EPUB no tiene una portada declarada para reemplazar.")

    return posixpath.normpath(posixpath.join(opf_dir, href))


def replace_cover(epub_bytes: bytes, cover_bytes: bytes) -> bytes:
    """Swaps the cover image file inside an EPUB's zip, leaving every other
    entry byte-for-byte untouched (round-tripping through ebooklib's object
    model instead can corrupt the NCX table of contents on rebuild)."""
    try:
        src = zipfile.ZipFile(io.BytesIO(epub_bytes))
    except zipfile.BadZipFile as e:
        raise ValueError("El archivo no parece un EPUB válido.") from e

    with src:
        opf_path = _find_opf_path(src)
        cover_path = _find_cover_image_path(src, opf_path)

        out_buf = io.BytesIO()
        with zipfile.ZipFile(out_buf, "w") as dst:
            for item in src.infolist():
                data = cover_bytes if item.filename == cover_path else src.read(item.filename)
                dst.writestr(item, data)

    return out_buf.getvalue()
