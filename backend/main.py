import asyncio
import io
import pathlib

from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from scraper import fetch_info, fetch_work
from epub_gen import build_epub, epub_filename, replace_cover
from pdf_gen import extract_pdf

DEFAULT_COVER = pathlib.Path(__file__).parent / "img" / "Portada Bunny.png"

app = FastAPI(title="Bake My Fic! API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your domain in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/info")
async def info(url: str = Form(...)):
    """Returns title, author and chapter count for a given AO3 URL."""
    try:
        data = await asyncio.to_thread(fetch_info, url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con AO3: {e}")
    return data


@app.post("/convert")
async def convert(
    url: str = Form(...),
    cover: UploadFile = File(None),
):
    """Fetches the work, builds an EPUB and streams it back."""
    cover_bytes = None
    if cover and cover.filename:
        cover_bytes = await cover.read()
    elif DEFAULT_COVER.exists():
        cover_bytes = DEFAULT_COVER.read_bytes()

    try:
        work = await asyncio.to_thread(fetch_work, url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con AO3: {e}")

    try:
        epub_bytes = await asyncio.to_thread(build_epub, work, cover_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando el EPUB: {e}")

    filename = epub_filename(work.title)
    return StreamingResponse(
        io.BytesIO(epub_bytes),
        media_type="application/epub+zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/pdf-to-epub")
async def pdf_to_epub(
    pdf: UploadFile = File(...),
    cover: UploadFile = File(None),
    title: str = Form(None),
    author: str = Form(None),
):
    """Builds an EPUB from an uploaded PDF and streams it back."""
    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="El archivo debe ser un .pdf")

    pdf_bytes = await pdf.read()

    cover_bytes = None
    if cover and cover.filename:
        cover_bytes = await cover.read()
    elif DEFAULT_COVER.exists():
        cover_bytes = DEFAULT_COVER.read_bytes()

    try:
        work = await asyncio.to_thread(extract_pdf, pdf_bytes, title, author)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo el PDF: {e}")

    try:
        epub_bytes = await asyncio.to_thread(build_epub, work, cover_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando el EPUB: {e}")

    filename = epub_filename(work.title)
    return StreamingResponse(
        io.BytesIO(epub_bytes),
        media_type="application/epub+zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/cover")
async def cover(
    epub: UploadFile = File(...),
    cover: UploadFile = File(...),
):
    """Replaces the cover of an uploaded EPUB and streams the result back."""
    if not epub.filename or not epub.filename.lower().endswith(".epub"):
        raise HTTPException(status_code=422, detail="El archivo debe ser un .epub")

    epub_bytes = await epub.read()
    cover_bytes = await cover.read()

    try:
        new_epub_bytes = await asyncio.to_thread(replace_cover, epub_bytes, cover_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cambiando la portada: {e}")

    return StreamingResponse(
        io.BytesIO(new_epub_bytes),
        media_type="application/epub+zip",
        headers={"Content-Disposition": f'attachment; filename="{epub.filename}"'},
    )
