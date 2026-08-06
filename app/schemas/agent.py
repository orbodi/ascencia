from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    external_user_id: str = Field(default="admin", max_length=80)
    channel: str = Field(default="api", max_length=40)
    teacher_id: int | None = None


class ChatResponse(BaseModel):
    reply: str
    model: str
    external_user_id: str
    channel: str
    teacher_id: int | None = None
