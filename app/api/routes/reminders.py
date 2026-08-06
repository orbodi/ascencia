from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_api_token
from app.schemas.reminders import ReminderSendRequest, ReminderSendResponse
from app.services.reminder_service import ReminderService

router = APIRouter(prefix="/reminders", dependencies=[Depends(require_api_token)])


@router.post("/send", response_model=ReminderSendResponse)
async def send_presence_reminders(
    body: ReminderSendRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> ReminderSendResponse:
    payload = body or ReminderSendRequest()
    result = await ReminderService(session).send_presence_confirmations(
        days_ahead=payload.days_ahead,
        on_date=payload.on_date,
    )
    return ReminderSendResponse(**result)
