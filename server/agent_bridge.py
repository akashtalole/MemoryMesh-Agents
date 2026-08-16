"""Normalizes chat streaming across the two backend modes into one async
generator of event dicts, so the API route and the frontend never need to
know which mode is active.

Both modes ultimately emit the same event shapes, because AgentCore mode is
just invoking the identical `Workflow.stream_query` running inside the
deployed container — see workflow.py / src/utils/stream.py for the event
vocabulary (agent_execution, text, reasoningText, tool).
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, Optional

logger = logging.getLogger(__name__)


class AgentBridge:
    async def stream(self, session_id: str, prompt: str) -> AsyncIterator[Dict[str, Any]]:
        raise NotImplementedError
        yield  # pragma: no cover - makes this an async generator for type checkers


class LocalWorkflowBridge(AgentBridge):
    """Runs the LangGraph workflow in this process — no AWS involved."""

    def __init__(self):
        self._workflow = None
        self._lock = asyncio.Lock()

    async def _get_workflow(self):
        if self._workflow is None:
            async with self._lock:
                if self._workflow is None:
                    from src.agents import Workflow

                    logger.info("LocalWorkflowBridge: initializing workflow (CockroachDB + Anthropic)...")
                    self._workflow = await Workflow.create()
        return self._workflow

    async def stream(self, session_id: str, prompt: str) -> AsyncIterator[Dict[str, Any]]:
        workflow = await self._get_workflow()
        async for raw in workflow.stream_query(session_id=session_id, prompt=prompt):
            payload = raw[len("data: "):].strip() if raw.startswith("data: ") else raw.strip()
            if not payload:
                continue
            try:
                yield json.loads(payload)
            except json.JSONDecodeError:
                yield {"type": "raw", "content": payload}


class AgentCoreBridge(AgentBridge):
    """Proxies chat requests to a deployed Amazon Bedrock AgentCore runtime.

    boto3's streaming iterator is blocking, so the invocation runs in a
    worker thread and pushes parsed chunks into an asyncio.Queue that the
    async generator drains — the standard sync-producer/async-consumer
    bridge pattern.
    """

    def __init__(self, runtime_arn: str, region: str):
        self.runtime_arn = runtime_arn
        self.region = region

    def _client(self):
        import boto3

        return boto3.client("bedrock-agentcore", region_name=self.region)

    def _invoke_sync(
        self,
        session_id: str,
        prompt: str,
        queue: "asyncio.Queue[Optional[Dict[str, Any]]]",
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        def put(item: Optional[Dict[str, Any]]) -> None:
            asyncio.run_coroutine_threadsafe(queue.put(item), loop)

        try:
            client = self._client()
            response = client.invoke_agent_runtime(
                agentRuntimeArn=self.runtime_arn,
                qualifier="DEFAULT",
                runtimeSessionId=session_id,
                payload=json.dumps({"prompt": prompt, "session_id": session_id}),
            )

            if "text/event-stream" in response.get("contentType", ""):
                for line in response["response"].iter_lines(chunk_size=1):
                    if not line:
                        continue
                    decoded = line.decode("utf-8")
                    if not decoded.startswith("data: "):
                        continue
                    payload = decoded[6:]
                    try:
                        put(json.loads(payload))
                    except json.JSONDecodeError:
                        put({"type": "raw", "content": payload})
            else:
                response_obj = response.get("response")
                content = response_obj.read() if hasattr(response_obj, "read") else response_obj
                if isinstance(content, bytes):
                    content = content.decode("utf-8")
                put({"type": "text", "content": str(content), "agent": "synthesizer"})
        except Exception as e:
            logger.error(f"AgentCore invocation failed: {e}")
            put({"type": "error", "content": str(e)})
        finally:
            put(None)

    async def stream(self, session_id: str, prompt: str) -> AsyncIterator[Dict[str, Any]]:
        queue: "asyncio.Queue[Optional[Dict[str, Any]]]" = asyncio.Queue()
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, self._invoke_sync, session_id, prompt, queue, loop)
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk
