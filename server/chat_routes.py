import json
import logging
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from server.schemas import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest):
    bridge = request.app.state.bridge
    session_id = body.session_id or str(uuid.uuid4())

    async def event_source():
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
        try:
            async for chunk in bridge.stream(session_id, body.prompt):
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            logger.error(f"chat_stream error (session={session_id}): {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
