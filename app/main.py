import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.api.router import api_router
from app.config import settings
from app.domain.db import AsyncSessionLocal
from app.services.autonomous_workflow import AutonomousWorkflowService

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


def _validate_production_settings() -> None:
    if settings.app_env.lower() not in {"production", "prod"}:
        return
    unsafe: list[str] = []
    if settings.jwt_secret.startswith("change-me"):
        unsafe.append("JWT_SECRET")
    if settings.api_token == "change-me":
        unsafe.append("API_TOKEN")
    if settings.admin_password == "admin123":
        unsafe.append("ADMIN_PASSWORD")
    if not settings.whatsapp_mock and not settings.whatsapp_app_secret:
        unsafe.append("WHATSAPP_APP_SECRET")
    if unsafe:
        raise RuntimeError(
            "Configuration de production refusée. Valeurs à sécuriser : "
            + ", ".join(unsafe)
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _validate_production_settings()
    logger.info(
        "Démarrage %s (env=%s, whatsapp_mock=%s, backoffice_dist=%s exists=%s)",
        settings.app_name,
        settings.app_env,
        settings.whatsapp_mock,
        DIST_DIR,
        INDEX_HTML.is_file(),
    )
    stop_event = asyncio.Event()
    task: asyncio.Task | None = None
    if settings.autonomous_mode_enabled:
        task = asyncio.create_task(_run_autonomous_scheduler(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        if task is not None:
            await task


async def _run_autonomous_scheduler(stop_event: asyncio.Event) -> None:
    logger.info(
        "Orchestration autonome active (publication_auto=%s, intervalle=%ss)",
        settings.autonomous_publish_enabled,
        settings.autonomous_poll_seconds,
    )
    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as session:
                result = await AutonomousWorkflowService(session).run_once()
                logger.info("Cycle autonome: %s", result["state"])
        except Exception:  # noqa: BLE001
            logger.exception("Le cycle autonome a échoué; nouvel essai au prochain passage")
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.autonomous_poll_seconds
            )
        except TimeoutError:
            pass


app = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/backoffice/", status_code=307)


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
