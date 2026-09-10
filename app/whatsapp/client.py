"""Client WhatsApp Cloud API (Meta) + mode mock."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    return "".join(ch for ch in phone if ch.isdigit())


class WhatsAppClient:
    def __init__(self) -> None:
        self.mock = settings.whatsapp_mock or not settings.whatsapp_token
        self.token = settings.whatsapp_token
        self.phone_number_id = settings.whatsapp_phone_number_id

    @property
    def graph_api_base(self) -> str:
        version = settings.whatsapp_graph_api_version.strip().lstrip("v")
        return f"https://graph.facebook.com/v{version}"

    @property
    def messages_url(self) -> str:
        return f"{self.graph_api_base}/{self.phone_number_id}/messages"

    async def send_text(self, to: str, body: str) -> dict[str, Any]:
        to_norm = normalize_phone(to)
        if self.mock:
            logger.info("[WHATSAPP_MOCK] text to=%s body=%s", to_norm, body)
            return {"ok": True, "mock": True, "to": to_norm, "body": body}

        if not self.phone_number_id:
            return {"ok": False, "error": "WHATSAPP_PHONE_NUMBER_ID manquant"}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_norm,
            "type": "text",
            "text": {"preview_url": False, "body": body[:4096]},
        }
        return await self._post_json(payload)

    async def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = "fr",
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Envoie un modèle Meta approuvé, y compris hors fenêtre de 24 heures."""
        to_norm = normalize_phone(to)
        if not to_norm:
            return {"ok": False, "error": "Numéro destinataire invalide"}
        if self.mock:
            logger.info(
                "[WHATSAPP_MOCK] template to=%s name=%s language=%s",
                to_norm,
                template_name,
                language_code,
            )
            return {
                "ok": True,
                "mock": True,
                "to": to_norm,
                "template": template_name,
                "language": language_code,
            }
        if not self.phone_number_id:
            return {"ok": False, "error": "WHATSAPP_PHONE_NUMBER_ID manquant"}

        template: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if components:
            template["components"] = components
        return await self._post_json(
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_norm,
                "type": "template",
                "template": template,
            }
        )

    async def send_document(
        self,
        to: str,
        file_path: str | Path,
        caption: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        path = Path(file_path)
        to_norm = normalize_phone(to)
        if self.mock:
            logger.info(
                "[WHATSAPP_MOCK] document to=%s path=%s caption=%s",
                to_norm,
                path,
                caption,
            )
            return {
                "ok": True,
                "mock": True,
                "to": to_norm,
                "path": str(path),
                "caption": caption,
            }

        if not path.exists():
            return {"ok": False, "error": f"Fichier introuvable: {path}"}

        media_id = await self._upload_media(path)
        if not media_id:
            return {"ok": False, "error": "Échec upload média WhatsApp"}

        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_norm,
            "type": "document",
            "document": {
                "id": media_id,
                "filename": filename or path.name,
            },
        }
        if caption:
            payload["document"]["caption"] = caption[:1024]
        return await self._post_json(payload)

    async def _upload_media(self, path: Path) -> str | None:
        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "application/octet-stream"
        url = f"{self.graph_api_base}/{self.phone_number_id}/media"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient(timeout=60) as client:
            with path.open("rb") as handle:
                files = {
                    "file": (path.name, handle, mime),
                    "messaging_product": (None, "whatsapp"),
                    "type": (None, mime),
                }
                response = await client.post(url, headers=headers, files=files)
        if response.status_code >= 400:
            logger.error("Upload WhatsApp échoué: %s", response.text)
            return None
        return response.json().get("id")

    async def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self.messages_url, headers=headers, json=payload
            )
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            logger.error("WhatsApp API error %s: %s", response.status_code, data)
            return {"ok": False, "status_code": response.status_code, "error": data}
        return {"ok": True, "mock": False, "response": data}
