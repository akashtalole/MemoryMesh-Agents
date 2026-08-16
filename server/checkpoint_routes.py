"""Time-travel over a session's LangGraph checkpoint history.

Every node transition in the workflow is already snapshotted into
CockroachDB by `AsyncCockroachDBSaver` (see src/memory/checkpointer.py) —
this module doesn't add new writes, it just reads that history back so the
UI can scrub through exactly how a conversation's state evolved, step by
step, node by node. That resumability is the entire point of checkpointing
a workflow into a real database instead of process memory; this is what
makes it visible.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["checkpoints"])

# Maps AgentState channel names (the keys LangGraph checkpoints) to a
# friendly node label, so a step's `updated_channels` can be summarized as
# "which agent(s) just ran" without needing per-version metadata.writes
# support (not present in every langgraph release).
CHANNEL_TO_LABEL: Dict[str, str] = {
    "similar_cases": "Memory recall",
    "orchestrator_state": "Orchestrator",
    "agent_task_map": "Orchestrator",
    "required_agents": "Orchestrator",
    "orchestrator_context": "Orchestrator",
    "security_monitor_state": "Security Monitor",
    "security_monitor_insights": "Security Monitor",
    "broker_monitor_state": "Broker Monitor",
    "broker_monitor_insights": "Broker Monitor",
    "risk_monitor_state": "Risk Monitor",
    "risk_monitor_insights": "Risk Monitor",
    "intel_analyst_state": "Intel Analyst",
    "intel_analyst_insights": "Intel Analyst",
    "memory_ops_state": "Memory Ops",
    "memory_ops_insights": "Memory Ops",
    "compliance_officer_state": "Compliance Officer",
    "compliance_officer_insights": "Compliance Officer",
    "case_triage_state": "Case Triage",
    "case_triage_insights": "Case Triage",
    "audit_reviewer_state": "Audit Reviewer",
    "audit_reviewer_insights": "Audit Reviewer",
    "synthesizer_state": "Synthesizer",
    "synthesizer_insights": "Synthesizer",
    "case_id": "Memory write-back",
}


async def _get_checkpointer():
    """Reuses the same module-level singleton the running workflow uses
    (in local mode) or lazily builds a read-only one (in AgentCore mode,
    where this process never runs the graph itself)."""
    from src.memory.checkpointer import build_checkpointer

    return await build_checkpointer()


def _node_labels(checkpoint: Dict[str, Any]) -> List[str]:
    if "__start__" in checkpoint.get("channel_values", {}):
        return ["Input received"]
    updated = checkpoint.get("updated_channels") or []
    labels = {CHANNEL_TO_LABEL[ch] for ch in updated if ch in CHANNEL_TO_LABEL}
    return sorted(labels) if labels else ["…"]


def _summarize_state(channel_values: Dict[str, Any]) -> Dict[str, Any]:
    """Trims a raw checkpoint state snapshot for the UI: full Strands
    message histories collapse to a count (they can be large), everything
    else — the actual AgentState fields — passes through as-is.
    """
    summary: Dict[str, Any] = {}
    for key, value in channel_values.items():
        if key.startswith("__") or key.startswith("branch:"):
            continue
        if key.endswith("_state") and isinstance(value, dict):
            messages = value.get("messages") or []
            summary[key] = {"message_count": len(messages)}
        elif key == "similar_cases" and isinstance(value, list):
            summary[key] = {
                "count": len(value),
                "cases": [
                    {"case_id": c.get("case_id"), "query": c.get("query"), "score": c.get("score")}
                    for c in value
                ],
            }
        else:
            summary[key] = value
    return summary


@router.get("/sessions/{session_id}/checkpoints")
async def list_checkpoints(session_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    limit = max(1, min(limit, 500))
    try:
        checkpointer = await _get_checkpointer()
        config = {"configurable": {"thread_id": session_id}}
        items = []
        async for ckpt in checkpointer.alist(config, limit=limit):
            labels = _node_labels(ckpt.checkpoint)
            # Skip LangGraph's internal "about to route" checkpoints — they
            # carry no application-level state change, just routing markers.
            if labels == ["…"]:
                continue
            items.append(
                {
                    "checkpoint_id": ckpt.config["configurable"]["checkpoint_id"],
                    "step": ckpt.metadata.get("step"),
                    "source": ckpt.metadata.get("source"),
                    "ts": ckpt.checkpoint.get("ts"),
                    "node_labels": labels,
                }
            )
    except Exception as e:
        logger.warning(f"list_checkpoints failed for session {session_id}: {e}")
        return []

    # alist yields newest-first; a scrubber reads left-to-right chronologically.
    items.reverse()
    return items


@router.get("/sessions/{session_id}/checkpoints/{checkpoint_id}")
async def get_checkpoint(session_id: str, checkpoint_id: str) -> Dict[str, Any]:
    try:
        checkpointer = await _get_checkpointer()
        config = {"configurable": {"thread_id": session_id, "checkpoint_id": checkpoint_id}}
        tup = await checkpointer.aget_tuple(config)
    except Exception as e:
        logger.warning(f"get_checkpoint failed for {session_id}/{checkpoint_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))

    if tup is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    return {
        "checkpoint_id": checkpoint_id,
        "step": tup.metadata.get("step"),
        "source": tup.metadata.get("source"),
        "ts": tup.checkpoint.get("ts"),
        "node_labels": _node_labels(tup.checkpoint),
        "state": _summarize_state(tup.checkpoint.get("channel_values", {})),
    }
