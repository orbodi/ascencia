from fastapi import APIRouter

from app.admin.routes import (
    autonomy,
    auth_routes,
    changes,
    chat,
    config_routes,
    courses,
    curriculum,
    dashboard,
    groups,
    history_admin,
    levels,
    outreach,
    planning_cycle,
    publications,
    presence_campaigns,
    rooms,
    schedule,
    teachers,
)

admin_router = APIRouter()
admin_router.include_router(autonomy.router)
admin_router.include_router(auth_routes.router)
admin_router.include_router(dashboard.router)
admin_router.include_router(levels.router)
admin_router.include_router(curriculum.router)
admin_router.include_router(publications.router)
admin_router.include_router(presence_campaigns.router)
admin_router.include_router(outreach.router)
admin_router.include_router(planning_cycle.router)
admin_router.include_router(teachers.router)
admin_router.include_router(groups.router)
admin_router.include_router(history_admin.router)
admin_router.include_router(rooms.router)
admin_router.include_router(courses.router)
admin_router.include_router(schedule.router)
admin_router.include_router(changes.router)
admin_router.include_router(config_routes.router)
admin_router.include_router(chat.router)
