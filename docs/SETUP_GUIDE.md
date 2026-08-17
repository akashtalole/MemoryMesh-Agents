# MemoryMesh Agent — Setup Guide

Step-by-step instructions for getting MemoryMesh Agent running, from a clean
checkout to a local demo to an AWS AgentCore deployment. For what the app
actually does once it's running, see [`USER_GUIDE.md`](USER_GUIDE.md). For
architecture and the hackathon write-up, see the [Home page](index.md).

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
git clone https://github.com/akashtalole/MemoryMesh-Agents.git
cd MemoryMesh-Agents

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
| `JUDGE_ACCESS_PASSWORD` | blank | Shared password gating the app for judges — blank means no login screen at all. See [§8, Restricting access before deploying publicly](#restricting-access-before-deploying-publicly) |
| `JUDGE_SESSION_TTL_HOURS` | `168` (7 days) | How long a judge's login lasts before the password is asked for again |
| `COOKIE_SECURE` | `true` | Set to `false` only when testing the login gate over plain HTTP (no TLS) locally |
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

### Alternative: build via AWS CodeBuild instead of local Docker

`make deploy` builds the ARM64 image locally, which means Docker Desktop
emulating `linux/arm64` through QEMU if you're on an x86 machine — slow, and
the most common source of AgentCore build failures/timeouts. If you'd
rather not deal with local Docker at all:

```bash
make deploy-codebuild
```

This runs `deployment/deploy-codebuild.sh`, which does everything `make
deploy` does, except the image is built on **AWS CodeBuild's native ARM64
compute** (`aws/codebuild/amazonlinux2-aarch64-standard`) instead of on your
machine — no emulation, no local Docker install required at all. Source
comes straight from this repo on GitHub
(`https://github.com/akashtalole/MemoryMesh-Agents`, `main` branch by
default) — CodeBuild clones it directly, so **this builds whatever's
currently pushed to GitHub, not your local working copy**. Push your changes
first (override the repo/branch with the `GITHUB_REPO_URL` / `GITHUB_BRANCH`
env vars if you're deploying from a fork or a different branch). Concretely,
it:

1. Runs the same IAM-role + ECR-repo prerequisites as `make deploy`
   (`deployment/prerequisites.sh`)
2. Creates (or updates) a CodeBuild project with a `GITHUB` source pointed
   at that repo/branch, and a narrowly-scoped service role — separate from
   the AgentCore runtime role, permitted only to push to that one ECR
   repository
3. Starts a build using `buildspec.yml` (repo root) — `docker login` to ECR,
   `docker build` (no `--platform` flag needed, the compute is already
   ARM64), `docker push` — and polls until it finishes, printing the
   CloudWatch log location on failure
4. Runs the same `deployment/deploy-runtime.py` as `make deploy` to create
   or update the AgentCore runtime with the freshly-pushed image

**One-time setup, before the first run:** CodeBuild's `GITHUB` source type
needs a GitHub source credential registered for your AWS account/region —
this is required even for a public repo, since it's how CodeBuild identifies
itself to GitHub. Either connect once via the console (CodeBuild → Settings
→ Source providers → Connect to GitHub) or run:

```bash
aws codebuild import-source-credentials --server-type GITHUB \
  --auth-type PERSONAL_ACCESS_TOKEN --token <your-github-PAT>
```

The script detects a missing credential and prints this same instruction if
you skip it and run `make deploy-codebuild` first.

Everything else — setting `ANTHROPIC_API_KEY`/`COCKROACHDB_URL` on the
runtime after deploying, `make status`/`make logs`/`make destroy` — works
identically regardless of which path built the image, since both just push
to the same ECR repo.

One-time AWS cost note: this adds a CodeBuild project, billed per build
minute (first 100 minutes/month free on `BUILD_GENERAL1_SMALL`) — negligible
for occasional hackathon-scale deploys.

**In a hurry, deploying from AWS CloudShell?**

```bash
git clone https://github.com/akashtalole/MemoryMesh-Agents.git
cd MemoryMesh-Agents
make deploy-cloudshell
```

`deployment/cloudshell_deploy.sh` does the whole thing in one command:
installs Python deps, prompts for `ANTHROPIC_API_KEY` / `COCKROACHDB_URL` /
an optional `JUDGE_ACCESS_PASSWORD` if you don't already have a `.env`,
registers the GitHub source credential above if it's missing, then runs
`deploy-codebuild.sh` — and now `deploy-runtime.py` forwards those `.env`
values straight onto the runtime as `environmentVariables=` on
create/update_agent_runtime, so there's no separate console trip afterward
to set them by hand.

**What this doesn't give you**, and the script says so at the end: the
AgentCore Runtime itself isn't a browsable URL — it only accepts
SigV4-signed requests, never a raw browser request. To actually hand judges
something to click, you still need to run the FastAPI + React app
(`server/`) somewhere public, pointed at this runtime (App Runner is the
fastest AWS option; any small always-on host works too via `make web-build
&& uvicorn server.main:app --host 0.0.0.0 --port 8000`). If you're tight on
time, running `make dev` locally against the deployed runtime — or just
demoing it locally end to end — is a perfectly fine judged demo; the AWS
deployment proves the architecture regardless of whether it's also
publicly hosted.

### Restricting access before deploying publicly

If this deployment is reachable from the open internet, anyone who finds
the URL can run up your Anthropic API bill — the chat endpoint calls the
model on every message. Set one env var before deploying to gate the whole
app behind a single shared password (see `server/auth.py`):

```bash
JUDGE_ACCESS_PASSWORD=some-password-you-hand-to-judges
```

Leave it unset for local dev — the gate is a complete no-op when it's
empty, so `make dev` stays open with no extra step. Once set, every `/api/*`
route except `/api/auth/*` and `/api/health` requires it; the frontend shows
a password screen automatically. Sessions last `JUDGE_SESSION_TTL_HOURS`
(default 7 days) and are stored in a signed cookie — rotating the password
(change the env var, redeploy) instantly invalidates every existing
session, since the signing key is derived from the password itself. There
are no accounts and nothing to provision; this is a judging-window gate,
not a real auth system.

**What a judge sees, end to end:**

1. Open the deployed URL. If `JUDGE_ACCESS_PASSWORD` is set, a single
   password field is shown instead of the app (nothing else loads first —
   no flash of the chat UI before the check completes).
2. Enter the password you handed out and submit. On success, a session
   cookie is set and the full app (Chat + Dashboard) loads immediately.
3. The session persists across page reloads and browser restarts for
   `JUDGE_SESSION_TTL_HOURS` — a judge only enters the password once per
   session lifetime, not on every visit.
4. A **Log Out** button in the header (top-right, next to the CockroachDB/
   AgentCore status badges) clears the session and returns to the password
   screen; useful for testing the login flow itself before sharing the URL.

**Testing the gate yourself before sharing the URL with judges:**

```bash
JUDGE_ACCESS_PASSWORD=test-password make dev   # or set it in .env
```

Open http://localhost:5173 — you should see the password screen instead of
the app. Log in with `test-password`, confirm the app loads and Log Out
returns you to the password screen, then set the real password for the
actual deployment. If cookies won't set locally over plain `http://`, add
`COOKIE_SECURE=false` to `.env` for this local check only — keep it `true`
(the default) for the real deployment, which should be HTTPS.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `RuntimeError: ANTHROPIC_API_KEY is not set` | `.env` not loaded or key missing | Confirm `.env` exists and the key is set |
| Header shows "CockroachDB offline" | Bad `COCKROACHDB_URL`, or cluster unreachable | Test with `psql "$COCKROACHDB_URL" -c "SELECT 1"` |
| Dashboard's Vector Memory Map is empty | No cases in `case_memory` yet | Run `make seed-memory`, or just chat a few times — every finished investigation writes itself into memory |
| `memory_ops` agent answers "MCP tools unavailable" | `COCKROACHDB_MCP_API_KEY` unset | Optional integration — create a service-account key in Cloud Console → Access → Service Accounts, or ignore it |
| `make deploy` fails at Docker build | Not building for ARM64, or Docker Desktop not running | AgentCore requires `--platform linux/arm64`; the script already passes this — make sure Docker Desktop is running with buildx support |
| Login screen loops / rejects the correct password | `JUDGE_ACCESS_PASSWORD` differs between what you typed and what's set on the running server, or the cookie can't be set | Double-check the env var on the actual running process (not just your local `.env`); if testing over plain HTTP, set `COOKIE_SECURE=false` — browsers refuse `Secure` cookies on non-HTTPS origins |
| Logged in, but everything still 401s | Cookie blocked by browser (third-party cookie settings) or by CORS | Confirm the frontend and API are same-origin (the normal setup — one FastAPI process serving both); cross-origin needs `CORS_ORIGINS` set to the exact frontend origin, not `*`, since credentialed CORS requests can't use a wildcard |
| Deployed runtime returns errors immediately | `ANTHROPIC_API_KEY` / `COCKROACHDB_URL` not set on the runtime | Set them as runtime env vars post-deploy — they're never baked into the image |
