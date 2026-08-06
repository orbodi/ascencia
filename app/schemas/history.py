from pydantic import BaseModel, Field


class HistoryQuery(BaseModel):
    kind: str = Field(
        default="all",
        description="all | confirmations | reschedules | reminders",
    )
    limit: int = Field(default=50, ge=1, le=200)
