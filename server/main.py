"""FastAPI layer between the web UI and the agents.

Why this exists: a browser can't safely call AWS AgentCore's
invoke_agent_runtime directly (it needs SigV4-signed requests with AWS
credentials that must never reach client-side JS). This service holds those
credentials server-side, gives the frontend one stable streaming chat
contract regardless of backend mode (see server/agent_bridge.py), and
exposes read-only CockroachDB memory endpoints for the UI's live memory
panel.

Run with:  uvicorn server.main:app --reload --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

from src.config.logging_config import configure_logging  # noqa: E402

configure_logging(force_console=True)
logger = logging.getLogger(__name__)

from server.agent_bridge import AgentCoreBridge, LocalWorkflowBridge  # noqa: E402
from server.chat_routes import router as chat_router  # noqa: E402
from server.checkpoint_routes import router as checkpoint_router  # noqa: E402
from server.config import get_backend_mode, get_region, get_runtime_arn  # noqa: E402
from server.memory_routes import router as memory_router  # noqa: E402
from server.vector_map_routes import router as vector_map_router  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    mode = get_backend_mode()
    if mode == "agentcore":
        arn = get_runtime_arn()
        logger.info(f"Chat backend: AgentCore runtime ({arn}, region={get_region()})")
        app.state.bridge = AgentCoreBridge(arn, get_region())
    else:
        logger.info("Chat backend: local in-process LangGraph workflow (no AgentCore configured)")
        app.state.bridge = LocalWorkflowBridge()
    yield


app = FastAPI(title="MemoryMesh Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(checkpoint_router)
app.include_router(vector_map_router)

# Serve the built frontend (web/dist) if present, so a single `uvicorn
# server.main:app` serves both the API and the UI. In frontend dev mode
# (`npm run dev`), Vite serves the UI itself and proxies /api to this
# service instead — see web/vite.config.ts.
_web_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if _web_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")
    logger.info(f"Serving built frontend from {_web_dist}")
else:
    logger.info("web/dist not found — run `make web-build`, or use `npm run dev` in web/ for local UI dev")
