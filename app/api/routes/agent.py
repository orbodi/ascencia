import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import AgentService
from app.api.deps import get_db, require_api_token
from app.schemas.agent import ChatRequest, ChatResponse

router = APIRouter(prefix="/agent", dependencies=[Depends(require_api_token)])


@router.post("/chat", response_model=ChatResponse)
async def agent_chat(
    body: ChatRequest,
    session: AsyncSession = Depends(get_db),
) -> ChatResponse:
    try:
        result = await AgentService(session).chat(
            body.message,
            external_user_id=body.external_user_id,
            channel=body.channel,
            teacher_id=body.teacher_id,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).exception("Échec du chat d'intégration")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="L'assistant n'a pas pu traiter la demande.",
        ) from exc

    return ChatResponse(**result)
