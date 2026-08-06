from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.admin.schemas_crud import TeacherIn, TeacherOut
from app.api.deps import get_db
from app.domain.models import AdminUser, Teacher

router = APIRouter(prefix="/admin/teachers", tags=["admin-teachers"])


@router.get("", response_model=list[TeacherOut])
async def list_teachers(
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> list[Teacher]:
    result = await session.execute(select(Teacher).order_by(Teacher.name))
    return list(result.scalars().all())


@router.post("", response_model=TeacherOut, status_code=status.HTTP_201_CREATED)
async def create_teacher(
    body: TeacherIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> Teacher:
    existing = await session.scalar(select(Teacher).where(Teacher.email == body.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email déjà utilisé")
    teacher = Teacher(**body.model_dump())
    session.add(teacher)
    await session.commit()
    await session.refresh(teacher)
    return teacher


@router.patch("/{teacher_id}", response_model=TeacherOut)
async def update_teacher(
    teacher_id: int,
    body: TeacherIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> Teacher:
    teacher = await session.get(Teacher, teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="Enseignant introuvable")
    for key, value in body.model_dump().items():
        setattr(teacher, key, value)
    await session.commit()
    await session.refresh(teacher)
    return teacher


@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_teacher(
    teacher_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> None:
    teacher = await session.get(Teacher, teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="Enseignant introuvable")
    teacher.is_active = False
    await session.commit()
