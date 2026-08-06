"""Webhook Meta WhatsApp Cloud API."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_api_token
from app.config import settings
from app.whatsapp.client import WhatsAppClient
from app.whatsapp.webhook_service import WhatsAppWebhookService, verify_meta_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook/whatsapp", tags=["whatsapp"])
admin_router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


class TestSendRequest(BaseModel):
    to: str = Field(description="Numéro destinataire, ex: 33610000001")
    message: str = Field(min_length=1, max_length=4096)


@router.get("")
async def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    """Handshake de vérification Meta (Subscribe)."""
    if (
        hub_mode == "subscribe"
        and hub_verify_token
        and hub_verify_token == settings.whatsapp_verify_token
    ):
        logger.info("Webhook WhatsApp vérifié")
        return PlainTextResponse(content=hub_challenge or "")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Verify token invalide",
    )


@router.post("")
async def receive_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Réception des messages WhatsApp → agent → réponse."""
    raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_meta_signature(raw, signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Signature WhatsApp invalide",
        )

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON invalide",
        ) from exc

    try:
        result = await WhatsAppWebhookService(session).handle_inbound(payload)
    except Exception:
        logger.exception("Erreur traitement webhook WhatsApp")
        return {"ok": False, "error": "processing_failed"}

    return result


@admin_router.post("/test-send", dependencies=[Depends(require_api_token)])
async def test_send_whatsapp(body: TestSendRequest) -> dict:
    """Envoie un message texte de test (mock ou Cloud API selon .env)."""
    return await WhatsAppClient().send_text(body.to, body.message)
