from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.admin.schemas_crud import GroupIn, GroupOut
from app.api.deps import get_db
from app.domain.models import AcademicLevel, AdminUser, StudentGroup

router = APIRouter(prefix="/admin/groups", tags=["admin-groups"])


@router.get("", response_model=list[GroupOut])
async def list_groups(
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> list[StudentGroup]:
    result = await session.execute(select(StudentGroup).order_by(StudentGroup.name))
    return list(result.scalars().all())


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> StudentGroup:
    if body.academic_level_id is not None:
        level = await session.get(AcademicLevel, body.academic_level_id)
        if level is None:
            raise HTTPException(status_code=400, detail="Niveau introuvable")
    group = StudentGroup(**body.model_dump())
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


@router.patch("/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: int,
    body: GroupIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> StudentGroup:
    group = await session.get(StudentGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Groupe introuvable")
    for key, value in body.model_dump().items():
        setattr(group, key, value)
    await session.commit()
    await session.refresh(group)
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> None:
    group = await session.get(StudentGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Groupe introuvable")
    await session.delete(group)
    await session.commit()
