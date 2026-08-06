from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "whatsapp_mock": settings.whatsapp_mock,
        "gemini_model": settings.gemini_model,
    }
