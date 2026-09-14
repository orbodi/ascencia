from datetime import date
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

    @property
    def phone_norm(self) -> str:
        return "".join(ch for ch in self.numero if ch.isdigit())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Geminia Schedule POC"
    app_env: str = "development"
    demo_mode: bool = True
    api_token: str = "change-me"

    # Orchestration autonome. La publication reste désactivée par défaut afin
    # qu'un déploiement ne diffuse jamais de planning sans choix explicite.
    autonomous_mode_enabled: bool = False
    autonomous_publish_enabled: bool = False
    autonomous_target_week_offset: int = 1
    autonomous_poll_seconds: int = Field(default=300, ge=30, le=86400)
    autonomous_reminder_hours: int = Field(default=24, ge=1, le=168)
    autonomous_max_reminders: int = Field(default=3, ge=1, le=20)
    autonomous_channels: str = "email,whatsapp"

    database_url: str = (
        "postgresql+asyncpg://geminia:geminia@localhost:5432/geminia"
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    whatsapp_mock: bool = True
    whatsapp_graph_api_version: str = "v23.0"
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = "geminia-verify"
    whatsapp_app_secret: str = ""
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:8000"]
    )

    email_mock: bool = True
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    availability_form_url: str = ""
    public_base_url: str = "http://localhost:8000"
    presence_response_hours: int = 48
    max_group_daily_minutes: int = 480
    whatsapp_presence_template_name: str = ""

    # Listes JSON : [{"nom":"...","prenom":"...","numero":"336...","role":"admin|teacher"}]
    whatsapp_admins: list[WhatsAppPerson] = Field(default_factory=list)
    whatsapp_teachers: list[WhatsAppPerson] = Field(default_factory=list)

    university_name: str = "Ascencia Keyce Togo"
    semester_label: str = "Semestre 1 — 2026"
    semester_number: int = 1
    # Lundi de la semaine 1 du semestre (pour EDT_S*_SEMAINE{n}_*.pdf).
    semester_start_date: date | None = None
    pdf_director_name: str = "Franck ASSOU"
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
