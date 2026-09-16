"""API admin — programmes pédagogiques multi-semaines."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.admin.schemas_crud import (
    CurriculumPlanCreate,
    CurriculumPlanOut,
    CurriculumPlanUpdate,
    CurriculumWeekReplace,
)
from app.api.deps import get_db
from app.domain.models import AdminUser
from app.services.curriculum_service import CurriculumService

router = APIRouter(prefix="/admin/curriculum-plans", tags=["admin-curriculum"])


@router.get("", response_model=list[CurriculumPlanOut])
async def list_curriculum_plans(
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    service = CurriculumService(session)
    plans = await service.list_plans()
    return [service.serialize(plan) for plan in plans]


@router.get("/{plan_id}", response_model=CurriculumPlanOut)
async def get_curriculum_plan(
    plan_id: int,
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = CurriculumService(session)
    plan = await service.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Programme introuvable")
    return service.serialize(plan)


@router.post("", response_model=CurriculumPlanOut, status_code=status.HTTP_201_CREATED)
async def create_curriculum_plan(
    body: CurriculumPlanCreate,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = CurriculumService(session)
    try:
        plan = await service.create_plan(
            academic_level_id=body.academic_level_id,
            semester=body.semester,
            week_count=body.week_count,
        )
    except ValueError as exc:
        detail = str(exc)
        code = 409 if "existe déjà" in detail else 400
        raise HTTPException(status_code=code, detail=detail) from exc
    return service.serialize(plan)


@router.patch("/{plan_id}", response_model=CurriculumPlanOut)
async def update_curriculum_plan(
    plan_id: int,
    body: CurriculumPlanUpdate,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = CurriculumService(session)
    try:
        plan = await service.update_plan(
            plan_id,
            week_count=body.week_count,
            semester=body.semester,
        )
    except ValueError as exc:
        detail = str(exc)
        code = 404 if "introuvable" in detail else 400
        if "existe déjà" in detail:
            code = 409
        raise HTTPException(status_code=code, detail=detail) from exc
    return service.serialize(plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_curriculum_plan(
    plan_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> None:
    service = CurriculumService(session)
    try:
        await service.delete_plan(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{plan_id}/weeks/{week_index}", response_model=CurriculumPlanOut)
async def replace_curriculum_week(
    plan_id: int,
    week_index: int,
    body: CurriculumWeekReplace,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = CurriculumService(session)
    try:
        plan = await service.replace_week_items(
            plan_id,
            week_index,
            [item.model_dump() for item in body.items],
        )
    except ValueError as exc:
        detail = str(exc)
        code = 404 if "introuvable" in detail else 400
        raise HTTPException(status_code=code, detail=detail) from exc
    return service.serialize(plan)
