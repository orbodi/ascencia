from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.auth import create_access_token, hash_password, verify_password
from app.admin.deps import require_admin_user, require_superadmin
from app.admin.schemas import (
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.api.deps import get_db
from app.domain.models import AdminUser

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await session.execute(
        select(AdminUser).where(AdminUser.username == body.username)
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé",
        )
    token = create_access_token(user.username, user.role.value, user.id)
    return TokenResponse(
        access_token=token,
        role=user.role.value,
        username=user.username,
    )


@router.get("/me", response_model=UserOut)
async def me(user: AdminUser = Depends(require_admin_user)) -> AdminUser:
    return user


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _user: AdminUser = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
) -> list[AdminUser]:
    result = await session.execute(select(AdminUser).order_by(AdminUser.id))
    return list(result.scalars().all())


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    _user: AdminUser = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
) -> AdminUser:
    existing = await session.execute(
        select(AdminUser).where(
            (AdminUser.username == body.username) | (AdminUser.email == body.email)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username ou email déjà utilisé",
        )
    user = AdminUser(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    _user: AdminUser = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
) -> AdminUser:
    user = await session.get(AdminUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    data = body.model_dump(exclude_unset=True)
    if "password" in data:
        user.hashed_password = hash_password(data.pop("password"))
    for key, value in data.items():
        setattr(user, key, value)
    await session.commit()
    await session.refresh(user)
    return user
