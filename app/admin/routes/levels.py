from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.admin.schemas_crud import LevelIn, LevelOut
from app.api.deps import get_db
from app.domain.models import AcademicLevel, AdminUser

router = APIRouter(prefix="/admin/levels", tags=["admin-levels"])


@router.get("", response_model=list[LevelOut])
async def list_levels(
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> list[AcademicLevel]:
    result = await session.execute(select(AcademicLevel).order_by(AcademicLevel.code))
    return list(result.scalars().all())


@router.post("", response_model=LevelOut, status_code=status.HTTP_201_CREATED)
async def create_level(
    body: LevelIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> AcademicLevel:
    existing = await session.scalar(
        select(AcademicLevel).where(AcademicLevel.code == body.code)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Code déjà utilisé")
    level = AcademicLevel(**body.model_dump())
    session.add(level)
    await session.commit()
    await session.refresh(level)
    return level


@router.patch("/{level_id}", response_model=LevelOut)
async def update_level(
    level_id: int,
    body: LevelIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> AcademicLevel:
    level = await session.get(AcademicLevel, level_id)
    if level is None:
        raise HTTPException(status_code=404, detail="Niveau introuvable")
    for key, value in body.model_dump().items():
        setattr(level, key, value)
    await session.commit()
    await session.refresh(level)
    return level


@router.delete("/{level_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_level(
    level_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> None:
    level = await session.get(AcademicLevel, level_id)
    if level is None:
        raise HTTPException(status_code=404, detail="Niveau introuvable")
    await session.delete(level)
    await session.commit()
