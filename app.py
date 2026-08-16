"""Streamlit demo client for the MemoryMesh Agent.

Talks to the deployed AgentCore runtime over boto3 (`bedrock-agentcore`
invoke API) and additionally opens a direct, read-only connection to
CockroachDB so the sidebar can show the agent's persistent memory —
case_memory and message_store — being written to in real time as you chat.
"""

import json
import os
import re

import boto3
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from src.config.config_manager import ConfigManager

st.set_page_config(page_title="MemoryMesh Agent", layout="wide", page_icon="🪳")

with st.container():
    col1, col2, col3 = st.columns([1, 6, 1])
    with col2:
        st.title("🪳 MemoryMesh Agent")
        st.caption("Market surveillance agents with persistent memory in CockroachDB, hosted on AWS Bedrock AgentCore")


def get_streamlit_session_id():
    try:
        ctx = get_script_run_ctx()
        if ctx is None:
            return "streamlit_session_unknown"
        return f"streamlit_{ctx.session_id}"
    except Exception:
        return "streamlit_session_fallback"


if "custom_session_id" not in st.session_state:
    st.session_state.custom_session_id = get_streamlit_session_id()


def render_content_blocks(content: str) -> None:
    parts = re.split(r"(```[\s\S]*?```)", content)
    for part in parts:
        if part.startswith("```") and part.endswith("```"):
            render_code_block(part)
        elif part.strip():
            st.markdown(part)


def render_code_block(block: str) -> None:
    lines = block.strip().split("\n")
    first_line = lines[0].strip("`").strip()
    content_lines = lines[1:-1] if len(lines) > 2 else []
    content = "\n".join(content_lines)

    if first_line.lower() == "json":
        try:
            st.json(json.loads(content))
        except json.JSONDecodeError:
            st.code(content, language="json")
    else:
        st.code(content, language=first_line.lower() if first_line else None)


def invoke_agentcore_workflow(prompt: str, session_id: str, runtime_arn: str, region: str = "us-east-1"):
    """Invoke AgentCore workflow via boto3 and yield streaming text chunks."""
    try:
        agentcore_client = boto3.client("bedrock-agentcore", region_name=region)
        response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            qualifier="DEFAULT",
            runtimeSessionId=session_id,
            payload=json.dumps({"prompt": prompt, "session_id": session_id}),
        )

        if "text/event-stream" in response.get("contentType", ""):
            for line in response["response"].iter_lines(chunk_size=1):
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    if data_str.strip():
                        yield data_str
                    continue

                if isinstance(data, dict):
                    if data.get("type") == "text" and "content" in data:
                        yield data["content"]
                    elif "role" in data and "content" in data:
                        content = data["content"]
                        if isinstance(content, list) and content:
                            item = content[0]
                            yield item.get("text", str(item)) if isinstance(item, dict) else str(item)
                        else:
                            yield str(content)
        else:
            response_obj = response.get("response")
            content = response_obj.read() if hasattr(response_obj, "read") else response_obj
            if isinstance(content, bytes):
                content = content.decode("utf-8")
            yield str(content)

    except Exception as e:
        yield f"Error invoking AgentCore: {str(e)}"


def render_memory_panel():
    """Live view into CockroachDB's persistent memory tables."""
    conn_string = os.getenv("COCKROACHDB_URL")
    if not conn_string:
        st.caption("Set COCKROACHDB_URL to preview stored memory here.")
        return

    try:
        import psycopg

        from src.memory.db import get_psycopg_dsn

        with psycopg.connect(get_psycopg_dsn(), connect_timeout=5) as conn:
            with conn.cursor() as cur:
                case_table = os.getenv("COCKROACHDB_CASE_MEMORY_TABLE", "case_memory")
                chat_table = os.getenv("COCKROACHDB_CHAT_HISTORY_TABLE", "message_store")

                cur.execute(f"SELECT count(*) FROM {case_table}")
                case_count = cur.fetchone()[0]
                cur.execute(f"SELECT count(*) FROM {chat_table}")
                turn_count = cur.fetchone()[0]

                st.metric("Cases in long-term memory", case_count)
                st.metric("Logged conversation turns", turn_count)

                # Recent-cases preview is best-effort: don't let an unknown
                # JSONB metadata column name hide the counts above, which
                # are schema-agnostic and always work.
                try:
                    cur.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = %s AND data_type = 'jsonb' LIMIT 1",
                        (case_table,),
                    )
                    meta_col_row = cur.fetchone()
                    if meta_col_row:
                        meta_col = meta_col_row[0]
                        cur.execute(
                            f"SELECT {meta_col}->>'query' AS q, {meta_col}->>'recorded_at' AS t "
                            f"FROM {case_table} ORDER BY t DESC LIMIT 5"
                        )
                        rows = cur.fetchall()
                        if rows:
                            st.caption("Most recent cases:")
                            for q, _t in rows:
                                st.text(f"• {q}"[:120])
                except Exception:
                    pass
    except Exception as e:
        st.caption(f"Memory preview unavailable: {e}")


if "workflow_messages" not in st.session_state:
    st.session_state.workflow_messages = []

try:
    config_manager = ConfigManager()
    runtime_arn = config_manager.get_runtime_arn()
    static_config = config_manager.get_static_config()
    region = static_config.get("aws", {}).get("region", "us-east-1")
except Exception as e:
    st.error(f"Configuration error: {str(e)}")
    st.info("Run `make deploy` to deploy the workflow to AgentCore first.")
    st.stop()

with st.sidebar:
    st.header("🎛️ Controls")

    if runtime_arn:
        st.success("✅ AgentCore Runtime Connected")
        with st.expander("Runtime Details"):
            st.code(runtime_arn)
            st.caption(f"Region: {region}")
    else:
        st.error("❌ No Runtime ARN Found")
        st.info("Run: make deploy")

    if st.button("🗑️ Clear Chat"):
        st.session_state.workflow_messages = []
        st.rerun()

    new_session_id = st.text_input(
        "Session ID:", value=st.session_state.custom_session_id, key="session_id_input"
    )
    if new_session_id != st.session_state.custom_session_id:
        st.session_state.custom_session_id = new_session_id
        st.rerun()

    st.divider()
    st.header("🐘 CockroachDB Memory")
    render_memory_panel()

session_id = st.session_state.custom_session_id

st.info(
    "⚙️ Orchestrator routes to security_monitor / broker_monitor / risk_monitor / "
    "intel_analyst / memory_ops. Every investigation is checkpointed, logged, and "
    "embedded into CockroachDB — try asking a similar question twice."
)

for message in st.session_state.workflow_messages:
    with st.chat_message(message["role"]):
        render_content_blocks(message["content"])

if prompt := st.chat_input("Ask me anything about market surveillance..."):
    if not runtime_arn:
        st.error("No runtime ARN configured. Please deploy the workflow first.")
        st.stop()

    st.session_state.workflow_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        buffer = []
        try:
            for chunk in invoke_agentcore_workflow(prompt, session_id, runtime_arn, region):
                if chunk:
                    buffer.append(chunk)
                    with response_placeholder.container():
                        render_content_blocks("".join(buffer) + " |")
            final_content = "".join(buffer)
            with response_placeholder.container():
                render_content_blocks(final_content)
        except Exception as e:
            final_content = f"Connection error: {str(e)}"
            response_placeholder.error(final_content)

        st.session_state.workflow_messages.append({"role": "assistant", "content": final_content})
