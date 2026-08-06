from fastapi import APIRouter

from app.admin.routes import (
    auth_routes,
    changes,
    chat,
    config_routes,
    courses,
    dashboard,
    groups,
    levels,
    rooms,
    schedule,
    teachers,
)

admin_router = APIRouter()
admin_router.include_router(auth_routes.router)
admin_router.include_router(dashboard.router)
admin_router.include_router(levels.router)
admin_router.include_router(teachers.router)
admin_router.include_router(groups.router)
admin_router.include_router(rooms.router)
admin_router.include_router(courses.router)
admin_router.include_router(schedule.router)
admin_router.include_router(changes.router)
admin_router.include_router(config_routes.router)
admin_router.include_router(chat.router)
