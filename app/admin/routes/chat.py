from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import require_admin_user
from app.agent import AgentService
from app.api.deps import get_db
from app.domain.models import AdminUser, ConversationHistory
from app.schemas.agent import ChatRequest, ChatResponse

router = APIRouter(prefix="/admin/chat", tags=["admin-chat"])

CHANNEL = "backoffice"


class HistoryMessage(BaseModel):
    id: int
    role: str
    content: str
    created_at: str | None = None


class HistoryResponse(BaseModel):
    messages: list[HistoryMessage]
    external_user_id: str
    channel: str


def _user_id(user: AdminUser) -> str:
    return f"bo:{user.username}"


@router.get("/history", response_model=HistoryResponse)
async def get_chat_history(
    limit: int = Query(default=100, ge=1, le=500),
    user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> HistoryResponse:
    external_user_id = _user_id(user)
    result = await session.execute(
        select(ConversationHistory)
        .where(
            ConversationHistory.channel == CHANNEL,
            ConversationHistory.external_user_id == external_user_id,
            ConversationHistory.role.in_(["user", "assistant"]),
        )
        .order_by(ConversationHistory.id.desc())
        .limit(limit)
    )
    rows = list(reversed(result.scalars().all()))
    return HistoryResponse(
        messages=[
            HistoryMessage(
                id=r.id,
                role=r.role,
                content=r.content,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
            for r in rows
        ],
        external_user_id=external_user_id,
        channel=CHANNEL,
    )


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_chat_history(
    user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    external_user_id = _user_id(user)
    await session.execute(
        delete(ConversationHistory).where(
            ConversationHistory.channel == CHANNEL,
            ConversationHistory.external_user_id == external_user_id,
        )
    )
    await session.commit()


@router.post("", response_model=ChatResponse)
async def admin_chat(
    body: ChatRequest,
    user: AdminUser = Depends(require_admin_user),
    session: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Chat agent authentifié JWT (pas besoin de X-API-Token)."""
    try:
        result = await AgentService(session).chat(
            body.message,
            external_user_id=body.external_user_id or _user_id(user),
            channel=body.channel or CHANNEL,
            teacher_id=body.teacher_id,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erreur agent: {exc}",
        ) from exc
    return ChatResponse(**result)
