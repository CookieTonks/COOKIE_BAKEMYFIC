import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def extract_work_id(url: str) -> int:
    match = re.search(r"/works/(\d+)", url)
    if not match:
        raise ValueError("URL de AO3 no válida. Debe ser archiveofourown.org/works/XXXXXX")
    return int(match.group(1))


@dataclass
class Chapter:
    title: str
    html: str


@dataclass
class WorkData:
    title: str
    author: str
    language: str
    summary: str
    chapters: list[Chapter]


def _fetch_html(work_id: int) -> str:
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    })

    url = f"https://archiveofourown.org/works/{work_id}?view_full_work=true"

    for attempt in range(3):
        try:
            r = sess.get(url, timeout=90)
        except requests.Timeout:
            if attempt < 2:
                time.sleep(8)
                continue
            raise RuntimeError("AO3 tardó demasiado en responder. Intenta de nuevo en unos segundos.")
        except requests.ConnectionError:
            if attempt < 2:
                time.sleep(5)
                continue
            raise RuntimeError("No se pudo conectar con AO3. Verifica tu conexión a internet.")

        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 20))
            if attempt < 2:
                time.sleep(wait)
                continue
            raise RuntimeError("AO3 está limitando las peticiones. Espera unos segundos e inténtalo de nuevo.")

        if r.status_code in (503, 502):
            if attempt < 2:
                time.sleep(10)
                continue
            raise RuntimeError(f"AO3 no está disponible en este momento (HTTP {r.status_code}). Intenta más tarde.")

        if "This work could have adult content" in r.text:
            r = sess.get(url + "&view_adult=true", timeout=90)

        if r.status_code == 404:
            raise LookupError(f"Obra {work_id} no encontrada en AO3.")
        if "This work is only available to registered users" in r.text:
            raise PermissionError("Esta obra requiere iniciar sesión en AO3.")
        if r.status_code != 200:
            raise RuntimeError(f"AO3 respondió con HTTP {r.status_code}. Intenta de nuevo.")

        return r.text

    raise RuntimeError("No se pudo conectar con AO3 tras varios intentos. Intenta más tarde.")


def _text(tag) -> str:
    return tag.get_text(strip=True) if tag else ""


def _parse_work(html: str) -> WorkData:
    soup = BeautifulSoup(html, "html.parser")

    title = _text(soup.select_one("h2.title.heading"))
    author = _text(soup.select_one("h3.byline a[rel='author']"))
    if not author:
        author = _text(soup.select_one("h3.byline"))

    lang_dd = soup.select_one("dd.language")
    language = lang_dd.get_text(strip=True) if lang_dd else "en"

    summary_bq = soup.select_one("div.summary blockquote")
    summary = str(summary_bq) if summary_bq else ""

    chapters: list[Chapter] = []
    chapter_divs = soup.select("div#chapters div.chapter")
    if chapter_divs:
        for div in chapter_divs:
            title_tag = div.select_one("h3.title")
            ch_title = _text(title_tag) if title_tag else ""
            content = div.select_one("div.userstuff")
            if not content:
                continue
            for landmark in content.select("h3.landmark"):
                landmark.decompose()
            chapters.append(Chapter(title=ch_title, html=str(content)))
    else:
        content = soup.select_one("div#chapters div.userstuff")
        if content:
            for landmark in content.select("h3.landmark"):
                landmark.decompose()
            chapters.append(Chapter(title=title, html=str(content)))

    if not chapters:
        raise RuntimeError("No se encontró contenido de capítulos en la obra.")

    return WorkData(
        title=title or "Sin título",
        author=author or "Desconocido",
        language=language,
        summary=summary,
        chapters=chapters,
    )


def fetch_info(url: str) -> dict:
    work_id = extract_work_id(url)
    html = _fetch_html(work_id)
    work = _parse_work(html)
    return {
        "title": work.title,
        "author": work.author,
    }


def fetch_work(url: str) -> WorkData:
    work_id = extract_work_id(url)
    html = _fetch_html(work_id)
    return _parse_work(html)
