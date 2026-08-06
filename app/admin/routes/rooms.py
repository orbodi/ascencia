from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.admin.schemas_crud import RoomIn, RoomOut
from app.api.deps import get_db
from app.domain.models import AdminUser, Room

router = APIRouter(prefix="/admin/rooms", tags=["admin-rooms"])


@router.get("", response_model=list[RoomOut])
async def list_rooms(
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> list[Room]:
    result = await session.execute(select(Room).order_by(Room.name))
    return list(result.scalars().all())


@router.post("", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
async def create_room(
    body: RoomIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> Room:
    room = Room(**body.model_dump())
    session.add(room)
    await session.commit()
    await session.refresh(room)
    return room


@router.patch("/{room_id}", response_model=RoomOut)
async def update_room(
    room_id: int,
    body: RoomIn,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> Room:
    room = await session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Salle introuvable")
    for key, value in body.model_dump().items():
        setattr(room, key, value)
    await session.commit()
    await session.refresh(room)
    return room


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: int,
    _user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> None:
    room = await session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Salle introuvable")
    await session.delete(room)
    await session.commit()
