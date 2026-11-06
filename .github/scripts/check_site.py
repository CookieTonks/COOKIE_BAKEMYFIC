"""Revisa que Bake My Fic! este funcionando. Sale con 1 si algo falla.

Solo usa la libreria estandar. Para correrlo en local:
    python .github/scripts/check_site.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE = os.environ.get("API_BASE", "https://bakemyfic-production.up.railway.app").rstrip("/")
SITE_URL = os.environ.get("SITE_URL", "https://bakemyfic.cookiecodes.com.mx")
EXPECTED_ROUTES = {"/health", "/info", "/convert", "/pdf-to-epub", "/cover"}

# Railway puede responder 502 mientras despierta el servidor.
ATTEMPTS = 5
RETRY_WAIT_SECONDS = 15
RETRY_STATUSES = {502, 503, 504}


def request(url, method="GET", headers=None):
    """Devuelve (status, body). Reintenta mientras el servidor despierta."""
    all_headers = {"User-Agent": "bake-my-fic-health-check", **(headers or {})}
    for attempt in range(1, ATTEMPTS + 1):
        req = urllib.request.Request(url, method=method, headers=all_headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUSES or attempt == ATTEMPTS:
                return e.code, e.read()
        except OSError:
            if attempt == ATTEMPTS:
                raise
        time.sleep(RETRY_WAIT_SECONDS)


def check_site():
    status, _ = request(SITE_URL)
    if status != 200:
        raise RuntimeError(f"respondio {status}")
    return "responde"


def check_health():
    status, body = request(f"{API_BASE}/health")
    if status != 200 or json.loads(body).get("ok") is not True:
        raise RuntimeError(f"respondio {status}: {body[:200]!r}")
    return "responde"


def check_routes():
    status, body = request(f"{API_BASE}/openapi.json")
    if status != 200:
        raise RuntimeError(f"respondio {status}")
    missing = EXPECTED_ROUTES - set(json.loads(body)["paths"])
    if missing:
        raise RuntimeError(f"faltan rutas: {', '.join(sorted(missing))}")
    return f"{len(EXPECTED_ROUTES)} rutas publicadas"


def check_pdf_route():
    # Sin archivo, la ruta real responde 422 y no gasta recursos convirtiendo.
    status, _ = request(f"{API_BASE}/pdf-to-epub", method="POST")
    if status != 422:
        raise RuntimeError(f"se esperaba 422 y respondio {status}")
    return "la ruta existe"


def check_railway_deploy():
    """Detecta un deploy fallido aunque el build viejo siga respondiendo."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    sha = os.environ.get("GITHUB_SHA")
    if not repo or not sha:
        return "omitido fuera de GitHub Actions"

    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    status, body = request(f"https://api.github.com/repos/{repo}/commits/{sha}/status", headers=headers)
    if status != 200:
        raise RuntimeError(f"GitHub respondio {status}")

    railway = [s for s in json.loads(body)["statuses"] if "BakeMyFic" in s["context"]]
    if not railway:
        return f"sin deploy registrado para {sha[:7]}"
    if any(s["state"] in ("failure", "error") for s in railway):
        raise RuntimeError(f"el deploy de {sha[:7]} fallo; puede seguir activo un build viejo")
    return f"{sha[:7]}: {railway[0]['state']}"


CHECKS = [
    ("Pagina", check_site),
    ("API /health", check_health),
    ("Rutas de la API", check_routes),
    ("/pdf-to-epub", check_pdf_route),
    ("Deploy en Railway", check_railway_deploy),
]


def main():
    ok = True
    lines = []
    for name, check in CHECKS:
        try:
            lines.append(f"- ✅ **{name}**: {check()}")
        except Exception as e:
            ok = False
            lines.append(f"- ❌ **{name}**: {e}")

    report = "\n".join(lines)
    sys.stdout.reconfigure(encoding="utf-8")
    print(report)
    if os.environ.get("REPORT_FILE"):
        with open(os.environ["REPORT_FILE"], "w", encoding="utf-8") as f:
            f.write(report + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
