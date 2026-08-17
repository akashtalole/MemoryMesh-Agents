"""Single source of truth for which .env/shell values get forwarded into a
deployed container's own environment.

Used by both deploy-runtime.py (AgentCore, via environmentVariables= on
create/update_agent_runtime) and build_web_container_def.py (ECS Express
Mode's --primary-container). Keeping this list in one place means adding a
setting to one deploy path can't silently leave it missing from the other —
exactly what happened when COCKROACHDB_MCP_API_KEY/COCKROACHDB_MCP_CLUSTER_ID
were only ever added to the AgentCore path's own hand-maintained list.
"""

RUNTIME_ENV_KEYS = [
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL_ID",
    "COCKROACHDB_URL",
    "COCKROACHDB_CLUSTER_ID",
    "COCKROACHDB_POOL_SIZE",
    "COCKROACHDB_POOL_MAX_OVERFLOW",
    "COCKROACHDB_CHAT_HISTORY_TABLE",
    "COCKROACHDB_CASE_MEMORY_TABLE",
    "CASE_MEMORY_RECALL_K",
    "CASE_MEMORY_SCORE_THRESHOLD",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "COCKROACHDB_MCP_URL",
    "COCKROACHDB_MCP_API_KEY",
    "COCKROACHDB_MCP_CLUSTER_ID",
    "CORS_ORIGINS",
    "JUDGE_ACCESS_PASSWORD",
    "JUDGE_SESSION_TTL_HOURS",
    "COOKIE_SECURE",
    "LOG_LEVEL",
]
