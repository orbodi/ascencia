from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.admin.schemas_crud import TeacherIn, TeacherOut
from app.api.deps import get_db
from app.domain.models import AdminUser, Availability, Course, PresenceRequest, Teacher
from app.whatsapp.client import normalize_phone

router = APIRouter(prefix="/admin/teachers", tags=["admin-teachers"])


def _normalize_teacher_payload(body: TeacherIn) -> dict:
    data = body.model_dump()
    data["name"] = data["name"].strip()
    data["email"] = str(data["email"]).strip().lower()
    phone = (data.get("phone_whatsapp") or "").strip()
    if not phone:
        data["phone_whatsapp"] = None
    else:
        digits = normalize_phone(phone)
        data["phone_whatsapp"] = f"+{digits}" if digits else None
    return data


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
    payload = _normalize_teacher_payload(body)
    if not payload["name"]:
        raise HTTPException(status_code=400, detail="Le nom est obligatoire")
    existing = await session.scalar(
        select(Teacher).where(Teacher.email == payload["email"])
    )
    if existing:
        raise HTTPException(status_code=409, detail="Email déjà utilisé")
    teacher = Teacher(**payload)
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
    payload = _normalize_teacher_payload(body)
    if not payload["name"]:
        raise HTTPException(status_code=400, detail="Le nom est obligatoire")
    clash = await session.scalar(
        select(Teacher).where(
            Teacher.email == payload["email"],
            Teacher.id != teacher_id,
        )
    )
    if clash:
        raise HTTPException(status_code=409, detail="Email déjà utilisé")
    for key, value in payload.items():
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


@router.delete("/{teacher_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def delete_teacher(
    teacher_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Suppression définitive (contrairement à `DELETE /{teacher_id}`, qui
    ne fait qu'archiver). Bloquée (409) si l'enseignant est encore assigné à
    des cours, pour ne pas casser l'intégrité référentielle du planning ; il
    faut d'abord réassigner ou supprimer ces cours. Les disponibilités et
    demandes de présence liées à l'enseignant, elles, sont de simples
    données de collecte : elles sont supprimées avec lui.
    """
    teacher = await session.get(Teacher, teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="Enseignant introuvable")
    course_count = await session.scalar(
        select(func.count())
        .select_from(Course)
        .where(Course.teacher_id == teacher_id)
    )
    if course_count:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cet enseignant est assigné à des cours : suppression "
                "définitive impossible. Réassignez ou supprimez d'abord "
                "ces cours, ou archivez l'enseignant."
            ),
        )
    await session.execute(
        delete(Availability).where(Availability.teacher_id == teacher_id)
    )
    await session.execute(
        delete(PresenceRequest).where(PresenceRequest.teacher_id == teacher_id)
    )
    await session.delete(teacher)
    await session.commit()
