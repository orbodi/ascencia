from fastapi import APIRouter

from app.admin import admin_router
from app.api.routes import agent, exports, health, history, reminders
from app.whatsapp.routes import admin_router as whatsapp_admin_router
from app.whatsapp.routes import router as whatsapp_router

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(agent.router, tags=["agent"])
api_router.include_router(reminders.router, tags=["reminders"])
api_router.include_router(history.router, tags=["history"])
api_router.include_router(exports.router, tags=["exports"])
api_router.include_router(whatsapp_router)
api_router.include_router(whatsapp_admin_router)
api_router.include_router(admin_router)
