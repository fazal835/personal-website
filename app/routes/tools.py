import os
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import anthropic

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/tools")


class ChatMessage(BaseModel):
    message: str


@router.get("/chat")
async def chat_ui(request: Request):
    return templates.TemplateResponse("tools/chat.html", {"request": request})


@router.post("/chat/send")
async def chat_send(payload: ChatMessage):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"reply": "ANTHROPIC_API_KEY is not configured."}

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": payload.message}],
    )
    return {"reply": message.content[0].text}
