# MemoryMesh Agent — Setup Guide

Step-by-step instructions for getting MemoryMesh Agent running, from a clean
checkout to a local demo to an AWS AgentCore deployment. For what the app
actually does once it's running, see [`USER_GUIDE.md`](USER_GUIDE.md). For
architecture and the hackathon write-up, see the [README](../README.md).

## 1. Prerequisites

| Requirement | Why | Notes |
|---|---|---|
| Python 3.11+ | Runs the agents + FastAPI backend | `python --version` |
| Node.js 18+ | Builds/runs the React UI | `node --version` |
| An [Anthropic API key](https://console.anthropic.com/) | Strands agents call Anthropic's API directly | No Bedrock model access needed |
| A CockroachDB cluster | All persistent memory lives here | [CockroachDB Cloud](https://cockroachlabs.cloud/) free tier, or `cockroach demo` / `cockroach start-single-node --insecure` locally |
| AWS CLI v2 + Docker Desktop (ARM64) | **Only** if you plan to deploy to AgentCore | Not needed for local dev |

## 2. Clone and install

```bash
git clone <this-repo-url>
cd MemoryMesh-AI/memorymesh-agent

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
```

## 3. Configure `.env`

Open `.env` and fill in, at minimum:

```bash
ANTHROPIC_API_KEY=sk-ant-...
COCKROACHDB_URL=cockroachdb://root@localhost:26257/defaultdb?sslmode=disable
```

Everything else in `.env.example` has a working default. The full list, and
what each one controls:

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — (required) | Agent reasoning |
| `ANTHROPIC_MODEL_ID` | `claude-sonnet-4-6` | Model used by every Strands agent |
| `COCKROACHDB_URL` | local insecure | Connection string for every memory table |
| `COCKROACHDB_POOL_SIZE` / `COCKROACHDB_POOL_MAX_OVERFLOW` | `10` / `20` | Connection pool sizing |
| `COCKROACHDB_CHAT_HISTORY_TABLE` | `message_store` | Audit-log table name |
| `COCKROACHDB_CASE_MEMORY_TABLE` | `case_memory` | Vector-memory table name |
| `CASE_MEMORY_RECALL_K` | `3` | How many similar past cases to recall per query |
| `CASE_MEMORY_SCORE_THRESHOLD` | `0.55` | Minimum similarity to count as a match |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `BAAI/bge-small-en-v1.5` / `384` | Local ONNX embedding model (no external API) |
| `COCKROACHDB_MCP_URL` / `COCKROACHDB_MCP_API_KEY` / `COCKROACHDB_MCP_CLUSTER_ID` | blank | CockroachDB Cloud Managed MCP Server — leave blank to run without the `memory_ops` agent's live cluster introspection (it degrades gracefully) |
| `AWS_REGION` | `us-east-1` | Only used by `make deploy` |
| `AGENTCORE_RUNTIME_ARN` | blank | Set once deployed, or leave blank for local dev |
| `AGENT_BACKEND_MODE` | `auto` | `local` forces in-process; `agentcore` forces proxying; `auto` picks based on whether an ARN is set |
| `CORS_ORIGINS` | `*` | Tighten this for a real deployment |
| `LOG_LEVEL`, `LOG_TO_CONSOLE`, `LOG_TO_FILE`, `LOG_DIRECTORY` | see `.env.example` | Logging |

## 4. Provision CockroachDB (skip if you already have a cluster)

```bash
make provision-cluster
```

This drives the `ccloud` CLI (`ccloud cluster create`, `ccloud cluster
sql-user create`, `ccloud cluster sql --connection-params`) to create a free
CockroachDB Cloud cluster and a SQL user, printing a ready-to-use connection
string. Requires `ccloud` to be installed and authenticated
(`ccloud auth login`) — see the [ccloud CLI docs](https://www.cockroachlabs.com/docs/cockroachcloud/ccloud-get-started)
if you don't have it yet. Paste the printed connection string into
`COCKROACHDB_URL` in `.env`.

If you'd rather provision from the CockroachDB Cloud Console, that's fine
too — this script is just automation, not a requirement.

## 5. Initialize the memory schema

```bash
make init-memory
```

Idempotent — safe to re-run. Creates/migrates every memory table:
`checkpoints` / `checkpoint_blobs` / `checkpoint_writes` (LangGraph state),
`message_store` (audit log), and `case_memory` with its distributed C-SPANN
vector index. Run this once against a fresh cluster before the first `make
dev` or deployment.

```bash
make seed-memory   # optional: seeds 3 past cases so recall has something to find on your very first query
```

## 6. Run it locally (no AWS required)

```bash
make dev
```

This starts the FastAPI backend on `:8000` and the Vite dev server on
`:5173` together — Ctrl-C stops both. Open **http://localhost:5173**.

With no `AGENTCORE_RUNTIME_ARN` set, the backend runs the LangGraph workflow
in-process (`AGENT_BACKEND_MODE=auto` resolves to local), so this is a
complete, working demo with zero AWS involvement.

Other ways to run it:

```bash
make api-dev       # FastAPI only, on :8000
make web-dev        # Vite dev server only, on :5173 (proxies /api to :8000)
python scripts/chat_cli.py   # terminal chat loop, no HTTP layer at all
make start-client    # legacy Streamlit UI on :8501
```

## 7. Verify it's working

- Open http://localhost:5173 — the header should show a green **CockroachDB
  connected** badge and an amber **Local** badge.
- Send a message in the Chat view (see the [User Guide](USER_GUIDE.md) for
  example queries) and confirm you get a streamed response with an agent
  pipeline graph underneath it.
- Switch to the Dashboard view and confirm the stat tiles and Vector Memory
  Map show data (they will if you ran `make seed-memory`).

If the CockroachDB badge is red, double check `COCKROACHDB_URL` and that
your cluster is reachable (`psql "$COCKROACHDB_URL" -c "SELECT 1"` is a
quick way to test the connection string outside the app).

## 8. Deploy to AWS Bedrock AgentCore

Only needed if you want a real AWS-hosted runtime instead of local dev.

```bash
make deploy
```

This runs `deployment/deploy.sh`, which:

1. Detects your AWS account ID (`aws sts get-caller-identity`)
2. Creates the IAM execution role + attaches the least-privilege permissions
   policy (`deployment/permissions-policy.json` — no `bedrock:InvokeModel`
   anywhere, since inference goes to Anthropic directly)
3. Creates an ECR repository
4. Builds the container **for ARM64** and pushes it
5. Runs `deployment/deploy-runtime.py`, which creates (or updates) the
   AgentCore Runtime and its `DEFAULT` endpoint via `boto3`, and writes the
   resulting ARN into `config/dynamic-config.yaml`

**After deploying**, set `ANTHROPIC_API_KEY` and `COCKROACHDB_URL` as
environment variables on the AgentCore runtime itself (via the AgentCore
console, or `update_agent_runtime`) — they are deliberately not baked into
the image.

Once `config/dynamic-config.yaml` has a runtime ARN, the *same* `make dev` /
`uvicorn server.main:app` command automatically proxies chat requests to
the deployed runtime instead of running the workflow in-process — no code
change, no UI change.

Other deployment commands:

```bash
make prerequisites   # IAM role + ECR repo only, no build/push/deploy
make status            # print current config + list AgentCore runtimes
make logs               # tail the runtime's CloudWatch logs
make destroy            # delete the runtime, and optionally the ECR repo / IAM role
```

For a single-process production-style run once deployed (serves the built
UI and the API from one FastAPI process):

```bash
make web-build
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `RuntimeError: ANTHROPIC_API_KEY is not set` | `.env` not loaded or key missing | Confirm `.env` exists in `memorymesh-agent/` and the key is set |
| Header shows "CockroachDB offline" | Bad `COCKROACHDB_URL`, or cluster unreachable | Test with `psql "$COCKROACHDB_URL" -c "SELECT 1"` |
| Dashboard's Vector Memory Map is empty | No cases in `case_memory` yet | Run `make seed-memory`, or just chat a few times — every finished investigation writes itself into memory |
| `memory_ops` agent answers "MCP tools unavailable" | `COCKROACHDB_MCP_API_KEY` unset | Optional integration — create a service-account key in Cloud Console → Access → Service Accounts, or ignore it |
| `make deploy` fails at Docker build | Not building for ARM64, or Docker Desktop not running | AgentCore requires `--platform linux/arm64`; the script already passes this — make sure Docker Desktop is running with buildx support |
| Deployed runtime returns errors immediately | `ANTHROPIC_API_KEY` / `COCKROACHDB_URL` not set on the runtime | Set them as runtime env vars post-deploy — they're never baked into the image |
