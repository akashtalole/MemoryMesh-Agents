#!/usr/bin/env python3
"""Builds the --primary-container JSON for deploy-ecs-web.sh.

Forwards the exact same RUNTIME_ENV_KEYS the AgentCore deploy path uses
(deploy-runtime.py, via runtime_env_keys.py) plus this deployment's own
AGENTCORE_RUNTIME_ARN / AGENT_BACKEND_MODE — one source of truth for "which
env vars matter" so adding a setting to one deploy path can't silently
leave it missing from the other (this is how COCKROACHDB_MCP_API_KEY and
COCKROACHDB_MCP_CLUSTER_ID ended up reaching AgentCore but not ECS).

Reads .env with python-dotenv, never bash `source` (which mangles values
containing $, `, ", #, spaces...). Real shell env vars take priority over
.env, matching every other script here.

Usage: build_web_container_def.py <image_uri> <port> <runtime_arn>
Run with cwd at the project root (deploy-ecs-web.sh already cds there).
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime_env_keys import RUNTIME_ENV_KEYS  # noqa: E402

from dotenv import dotenv_values  # noqa: E402

image, port, runtime_arn = sys.argv[1:4]

dotenv_path = Path.cwd() / ".env"
file_values = dotenv_values(dotenv_path) if dotenv_path.exists() else {}


def resolve(key: str) -> str:
    return os.environ.get(key) or file_values.get(key) or ""


env = [
    {"name": "AGENTCORE_RUNTIME_ARN", "value": runtime_arn},
    {"name": "AGENT_BACKEND_MODE", "value": "agentcore"},
]
for key in RUNTIME_ENV_KEYS:
    # ANTHROPIC_API_KEY is deliberately never forwarded here: this service
    # only proxies chat requests to the already-deployed AgentCore runtime,
    # it never runs the workflow (and therefore never calls Anthropic)
    # itself.
    if key == "ANTHROPIC_API_KEY":
        continue
    value = resolve(key)
    if value:
        env.append({"name": key, "value": value})

print(json.dumps({"image": image, "containerPort": int(port), "environment": env}))
