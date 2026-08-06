from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WhatsAppPerson(BaseModel):
    nom: str
    prenom: str
    numero: str
    role: str = "teacher"

    @property
    def full_name(self) -> str:
        return f"{self.prenom} {self.nom}".strip()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Geminia Schedule POC"
    app_env: str = "development"
    api_token: str = "change-me"

    database_url: str = (
        "postgresql+asyncpg://geminia:geminia@localhost:5432/geminia"
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    whatsapp_mock: bool = True
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = "geminia-verify"
    whatsapp_app_secret: str = ""

    # Listes JSON : [{"nom":"...","prenom":"...","numero":"336...","role":"admin|teacher"}]
    whatsapp_admins: list[WhatsAppPerson] = Field(default_factory=list)
    whatsapp_teachers: list[WhatsAppPerson] = Field(default_factory=list)

    university_name: str = "Université Démo"
    semester_label: str = "Semestre 1 — 2026"
    reminder_days_ahead: int = 3

    jwt_secret: str = "change-me-jwt-secret-geminia"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8
    admin_username: str = "admin"
    admin_password: str = "admin123"
    admin_email: str = "admin@geminia.local"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
