from pydantic import BaseModel, Field

from app.admin.email_field import DemoEmailStr
from app.domain.models import AdminRole


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: AdminRole
    is_active: bool

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: DemoEmailStr
    password: str = Field(min_length=6, max_length=128)
    role: AdminRole = AdminRole.admin


class UserUpdate(BaseModel):
    email: DemoEmailStr | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)
    role: AdminRole | None = None
    is_active: bool | None = None
