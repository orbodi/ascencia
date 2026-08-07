import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from app.api.router import api_router
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _resolve_dist_dir() -> Path:
    env = os.environ.get("BACKOFFICE_DIST_DIR", "").strip()
    candidates = []
    if env:
        candidates.append(Path(env))
    # Image Docker (hors bind-mount /app)
    candidates.append(Path("/opt/ascencia/frontend/dist"))
    # Dev local / ancien emplacement
    candidates.append(Path(__file__).resolve().parent.parent / "frontend" / "dist")
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    return candidates[0]


DIST_DIR = _resolve_dist_dir()
INDEX_HTML = DIST_DIR / "index.html"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "Démarrage %s (env=%s, whatsapp_mock=%s, backoffice_dist=%s exists=%s)",
        settings.app_name,
        settings.app_env,
        settings.whatsapp_mock,
        DIST_DIR,
        INDEX_HTML.is_file(),
    )
    yield


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


def _missing_dist_html() -> HTMLResponse:
    return HTMLResponse(
        status_code=503,
        content="""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"/><title>Ascencia</title></head>
<body style="font-family:system-ui;max-width:40rem;margin:3rem auto;padding:0 1rem;line-height:1.5">
  <h1>Back-office non buildé</h1>
  <p>Aucun <code>index.html</code> trouvé (chemins essayés : <code>/opt/ascencia/frontend/dist</code>, <code>frontend/dist</code>).</p>
  <p>Relancez avec <code>docker compose up -d --build</code> (le front est buildé dans l'image).</p>
</body></html>""",
    )


@app.get("/backoffice")
@app.get("/backoffice/")
async def backoffice_index():
    if not INDEX_HTML.is_file():
        return _missing_dist_html()
    return FileResponse(INDEX_HTML)


@app.get("/backoffice/{full_path:path}")
async def backoffice_spa(full_path: str):
    if not DIST_DIR.is_dir():
        return _missing_dist_html()
    candidate = (DIST_DIR / full_path).resolve()
    try:
        candidate.relative_to(DIST_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    if candidate.is_file():
        return FileResponse(candidate)
    if INDEX_HTML.is_file():
        return FileResponse(INDEX_HTML)
    return _missing_dist_html()
