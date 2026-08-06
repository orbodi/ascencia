from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user, require_admin_write
from app.admin.schemas_crud import ConfigItem, ConfigUpdate
from app.api.deps import get_db
from app.domain.models import AdminUser, SystemConfig

router = APIRouter(prefix="/admin/config", tags=["admin-config"])


@router.get("", response_model=list[ConfigItem])
async def list_config(
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> list[SystemConfig]:
    result = await session.execute(select(SystemConfig).order_by(SystemConfig.key))
    return list(result.scalars().all())


@router.get("/{key}", response_model=ConfigItem)
async def get_config(
    key: str,
    _user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> SystemConfig:
    row = await session.scalar(select(SystemConfig).where(SystemConfig.key == key))
    if row is None:
        raise HTTPException(status_code=404, detail="Clé introuvable")
    return row


@router.put("/{key}", response_model=ConfigItem)
async def upsert_config(
    key: str,
    body: ConfigUpdate,
    user: AdminUser = Depends(require_admin_write),
    session: AsyncSession = Depends(get_db),
) -> SystemConfig:
    row = await session.scalar(select(SystemConfig).where(SystemConfig.key == key))
    if row is None:
        row = SystemConfig(key=key, value=body.value, updated_by=user.username)
        session.add(row)
    else:
        row.value = body.value
        row.updated_by = user.username
    await session.commit()
    await session.refresh(row)
    return row
