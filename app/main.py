import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "Démarrage %s (env=%s, whatsapp_mock=%s)",
        settings.app_name,
        settings.app_env,
        settings.whatsapp_mock,
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

if DIST_DIR.exists():
    assets = DIST_DIR / "assets"
    if assets.exists():
        app.mount(
            "/backoffice/assets",
            StaticFiles(directory=str(assets)),
            name="backoffice-assets",
        )

    @app.get("/backoffice")
    @app.get("/backoffice/")
    @app.get("/backoffice/{full_path:path}")
    async def backoffice_spa(full_path: str = "") -> FileResponse:
        # Ne pas servir index pour chemins d'API (sécurité)
        candidate = DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST_DIR / "index.html")
