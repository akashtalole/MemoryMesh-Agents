from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = Field(default=None, description="Conversation/thread id; generated if omitted")
