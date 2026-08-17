# Devpost Submission — Market Memory Mesh Agents

Copy-paste ready content for each Devpost form field. Character counts noted
where Devpost enforces a limit; trim quotes if your exact remaining-character
count differs from what's shown here.

---

## Project name

```
Market Memory Mesh Agents
```
(25 characters)

---

## Elevator pitch

Pick whichever fits your character budget — all three make the same claim.

**Primary (118 characters):**
```
An AI market-surveillance team that remembers every case it's worked — because its memory lives in CockroachDB, not RAM.
```

**Shorter (96 characters):**
```
A market-surveillance agent team whose memory is CockroachDB — so it never forgets, never resets.
```

**Shortest (79 characters):**
```
Multi-agent market surveillance with memory that survives — in CockroachDB.
```

---

## Project story

### Inspiration

Most multi-agent demos treat "memory" as a chat-history footnote — a buffer
that resets the moment the process restarts, in a domain where nobody's
livelihood depends on it remembering correctly. Market surveillance is the
opposite kind of domain: an investigation team needs to know whether a
pattern has been seen before, across *every* case anyone has ever worked,
not just the current conversation — and a regulator needs an immutable,
queryable record of exactly what was asked and answered, indefinitely.

We started from AWS's own reference architecture,
["Market Surveillance Agent with LangGraph and Strands on AgentCore"](https://aws.amazon.com/blogs/machine-learning/market-surveillance-agent-with-langgraph-and-strands-on-agentcore/),
and asked a deliberately provocative question for the CockroachDB × AWS
Hackathon: what if the memory layer wasn't a bolt-on cache sitting next to
the real system of record, but *was* the system of record — one database,
under transactional guarantees, holding conversation state, audit history,
and semantic case memory all at once? And what if that database was one
built to survive the kind of infrastructure failure a compliance system
can't afford to go down during?

### What it does

You ask a market-surveillance question — "What was the trading activity for
AAPL on March 15, 2024, and which brokers were most active?" — and an
orchestrator built on LangGraph routes it to the right specialist agents out
of eight: `security_monitor`, `broker_monitor`, `risk_monitor`,
`intel_analyst`, `compliance_officer`, `case_triage`, `audit_reviewer`, and
`memory_ops`. Each one reasons through a Strands Agent calling Anthropic's
API directly.

The part that makes this more than a chatbot: **before the orchestrator ever
sees your question, the system asks its own memory whether it's seen
something like it before** — a real semantic similarity search over every
past investigation, using CockroachDB's native `VECTOR` type and its
distributed C-SPANN index. If it finds something, that context shapes how
the question gets routed and answered. When the investigation finishes, the
finding is embedded and written back, so the system's memory compounds with
every use instead of resetting per session.

Two agents put that memory directly in their own hands, as a tool call
rather than something the graph does automatically: `case_triage` explicitly
queries case memory to decide how urgent the current investigation is based
on how similar past ones resolved, and `memory_ops` is wired to the
**CockroachDB Cloud Managed MCP Server** so it can answer "how many cases do
we have on file for this broker?" by actually querying the live cluster,
read-only.

Everything is checkpointed after every graph node (a crash or an
AgentCore replica restart mid-investigation resumes exactly where it
stopped) and every completed turn is written to a separate, human-readable
audit table a compliance reviewer could `SELECT * FROM` directly.

A modern React UI makes all of this visible instead of an implementation
detail: a streaming Chat view with a live agent-pipeline graph and
explainable citations, and a Dashboard with a **Vector Memory Map** — every
case embedding projected to 2D and searchable live — and a **Time Travel**
scrubber over a session's actual LangGraph checkpoint history.

### How we built it

The market-surveillance domain — agent personas, mock report catalog,
report schemas — is forked from AWS's public sample,
["Market Surveillance Agent with LangGraph and Strands on AgentCore"](https://aws.amazon.com/blogs/machine-learning/market-surveillance-agent-with-langgraph-and-strands-on-agentcore/).
Everything about *memory* and *model inference* was built fresh for this
hackathon:

- **LangGraph** orchestrates the whole thing as a `StateGraph`: a
  `recall_case_memory` node runs before the orchestrator, specialist agents
  fan out and back in, a synthesizer writes the final answer, and a
  `persist_case_memory` node closes the loop.
- **Strands Agents** do the reasoning, each backed by an `AnthropicModel`
  pointed straight at Anthropic's API — Bedrock is never in the inference
  path.
- **CockroachDB** is the only system of record, doing three distinct jobs:
  `AsyncCockroachDBSaver` for LangGraph's own checkpoint state,
  `CockroachDBChatMessageHistory` for the durable audit log, and
  `AsyncCockroachDBVectorStore` (backed by a C-SPANN distributed vector
  index) for long-term semantic case memory.
- **Amazon Bedrock AgentCore** is the only AWS service in the whole stack,
  and it's used purely to host the runtime: `api.py` wraps the LangGraph
  workflow in a `BedrockAgentCoreApp` entrypoint, and `deployment/` builds
  the container, pushes it to ECR, and provisions the AgentCore runtime.
- A **FastAPI** layer sits between the React UI and the agents, because a
  browser can't safely hold AWS credentials to call AgentCore's
  `invoke_agent_runtime` directly. It gives the UI one streaming chat
  contract regardless of whether the backend is running the workflow
  in-process (local dev, zero AWS) or proxying to a deployed AgentCore
  runtime — same UI, same API, no code changes to switch.
- The **ccloud CLI** provisions the CockroachDB Cloud cluster and SQL user
  end to end from the terminal, with JSON output at every step.
- The **React + Vite + TypeScript + Tailwind** UI's charts are hand-rolled
  (no charting library) against a categorical palette validated for a dark
  surface and colorblind accessibility.

### Challenges we ran into

- **A silently broken recall path.** `AsyncCockroachDBVectorStore`'s
  `asimilarity_search_with_relevance_scores()` raises `NotImplementedError`
  in the installed `langchain-cockroachdb` version — and our own code had it
  wrapped in a broad `try/except` that logged a warning and returned an
  empty list. Recall was silently failing shut on every single call, with
  nothing anywhere in the app surfacing that it was broken — the exact
  failure mode you'd never catch from a demo that "looked fine." We found it
  while double-checking the project's own central claim before writing this
  submission, and fixed it by switching to
  `asimilarity_search_with_score()` (raw cosine distance, since the store
  uses `DistanceStrategy.COSINE`) and converting to a similarity score
  ourselves.
- **Distributed vector indexing needs a cluster setting turned on first** —
  `CREATE VECTOR INDEX` fails outright until
  `feature.vector_index.enabled` is set, which isn't obvious from the
  CREATE INDEX syntax alone.
- **A real API-drift bug**: `ainit_vectorstore_table()` was being called
  with `distance_strategy=` and `overwrite_existing=` keyword arguments that
  don't exist on the installed library's actual signature — a `TypeError`
  on every single startup until we read the installed source directly to
  find the real parameter list.
- **Windows compatibility**: psycopg's async driver refuses to run under
  Windows' default `ProactorEventLoop` outright. Fixed with a small,
  explicit `WindowsSelectorEventLoopPolicy` switch applied as early as
  possible in every entrypoint — the FastAPI server and every standalone
  script.
- **A nested-event-loop bug** in our own schema-init script: a synchronous
  convenience wrapper in the chat-history library calls `asyncio.run()`
  internally, which raises when called from code that's already inside a
  running event loop. Fixed by awaiting the library's async implementation
  directly instead of the sync wrapper.
- **Keeping AWS honestly out of the inference path.** It's easy to *say*
  "Bedrock isn't used for inference" — we made sure it was actually true by
  checking that the deployment IAM policy carries no `bedrock:InvokeModel`
  permission at all, so the architecture can't quietly regress to using
  Bedrock without a visible permissions change.

### Accomplishments that we're proud of

- **CockroachDB as the only memory system in the stack** — no Redis, no
  separate vector database, no AgentCore Memory. Three genuinely different
  jobs (workflow checkpointing, audit history, semantic recall) done by one
  database under one set of transactional guarantees.
- **Finding and fixing a real, ship-blocking bug** in the project's central
  feature before treating the submission as done, instead of demoing a path
  that silently did nothing.
- Turning "introspect your own memory cluster" into an actual tool call —
  the `memory_ops` agent answers questions about its own infrastructure by
  querying it live through the CockroachDB Cloud Managed MCP Server, not by
  guessing.
- A UI that makes a distributed vector index something you can *look at* —
  the Vector Memory Map is a real, live, searchable 2D projection of the
  actual embeddings backing recall, not a static illustration.
- One codebase, two deployment modes, zero behavior difference: `make dev`
  runs the exact same LangGraph workflow with zero AWS involved, and
  `make deploy` puts the identical workflow behind AgentCore — the UI can't
  tell the difference.

### What we learned

- A `try/except` around an async library call that only logs a warning is
  exactly how a broken feature ships looking like a working one — test the
  actual return value against the exact installed library version, not just
  that the call doesn't raise in your dev loop's happy path.
- Running vector search on the same OLTP database that holds your
  operational data is a genuinely different value proposition from bolting
  on a dedicated vector database: the fact "this investigation happened" and
  the fact "this investigation is now recallable" become transactionally
  consistent for free.
- Async Postgres-wire drivers and Windows' default event loop don't mix by
  default, and you won't discover that from a Linux development machine —
  it's worth testing (or at least defensively coding for) cross-platform
  from day one.
- Least-privilege IAM is worth enforcing as a literal grep of the policy
  file at review time, not just an architectural intention that's easy to
  quietly violate later.

### What's next for Market Memory Mesh Agents

- Benchmark C-SPANN recall latency at real scale (thousands of cases, not
  a handful of seeded demos) and tune the index's build parameters
  accordingly.
- Give `case_triage` and `compliance_officer` real write-capable tools
  behind a human-in-the-loop approval step — compliance actions need
  sign-off, not just a recommendation.
- Explore multi-region CockroachDB placement for the audit trail itself, so
  the compliance record survives losing an entire cloud region, not just a
  single node.
- Replace the mock report catalog with real market-data connectors.
- Broaden the MCP toolset beyond CockroachDB's own MCP server to other
  compliance-relevant, read-only data sources.

---

## Built With

*(Add these one at a time into Devpost's "Built With" tag field — it
autocompletes/creates tags as you type, so paste them individually rather
than as one block.)*

```
python
typescript
react
vite
tailwindcss
fastapi
langgraph
langchain
strands-agents-sdk
anthropic-claude
claude
cockroachdb
cockroachdb-cloud
distributed-sql
postgresql
vector-search
psycopg
fastembed
boto3
aws
amazon-bedrock-agentcore
docker
amazon-ecr
mcp
```

Grouped, for reference:
- **Languages:** Python, TypeScript
- **Frontend:** React, Vite, Tailwind CSS
- **Agent orchestration:** LangGraph, LangChain, Strands Agents SDK
- **Model inference:** Anthropic Claude (via the Anthropic API, called
  directly — no Bedrock model invocation)
- **Backend:** FastAPI
- **Database:** CockroachDB / CockroachDB Cloud (checkpointing, audit log,
  and C-SPANN distributed vector index for semantic case memory), accessed
  via `langchain-cockroachdb` + `psycopg`
- **Embeddings:** fastembed (local ONNX, no external embedding API)
- **Cloud/hosting:** AWS (`boto3`), Amazon Bedrock AgentCore (runtime
  hosting only), Amazon ECR, IAM
- **Protocols:** Model Context Protocol (MCP) — the CockroachDB Cloud
  Managed MCP Server, wired into the `memory_ops` agent
- **Containerization:** Docker (ARM64 build for AgentCore)

---

## CockroachDB + AWS component integration

*(Paste this into the "how your project meaningfully integrated the
selected components" field.)*

This project uses CockroachDB for **three** of the hackathon's four required
components, plus two additional CockroachDB-backed memory stores beyond the
checklist, and exactly **one** AWS service, used only where it's meant to be
used.

**Distributed Vector Indexing** is the mechanism the entire "agentic memory"
claim rests on, not a bolted-on feature. Every finished investigation is
embedded locally (no external embedding API) and written to a `VECTOR`
column in `case_memory`, backed by a distributed **C-SPANN** index. That
index is read on the critical path of *every single incoming request* —
`recall_case_memory` runs before the orchestrator decides how to route a
question — and written to on the critical path of every completed one,
via `persist_case_memory` after synthesis. It's also queried a second,
independent way: the `case_triage` agent calls
`recall_similar_investigations` itself, mid-reasoning, to set investigation
priority — a genuinely agent-driven use of the index, not just an automatic
pipeline step.

**The CockroachDB Cloud Managed MCP Server** is wired directly into the
`memory_ops` Strands agent as an `MCPClient` bound to
`https://cockroachlabs.cloud/mcp` with a service-account bearer token. When
a user asks something like "how many cases do we have on file for this
broker?", that agent calls real, read-only MCP tools (`list_tables`,
`get_table_schema`, `select_query`, `show_running_queries`) against the live
cluster to answer — not a cached count, not a mock. There's a deliberate
symmetry here: the cluster this agent introspects is the same cluster
holding the system's own memory, so the agent can reason about the health of
the very thing it remembers with.

**The ccloud CLI** provisions the CockroachDB Cloud cluster this entire
project runs on, end to end from the terminal (`scripts/provision_cluster.sh`)
— cluster creation, SQL user creation, and connection-string retrieval, each
step emitting JSON, the same automation-friendly interface an agent could
drive itself rather than a human reading a console UI.

Two more CockroachDB-backed stores round out the memory layer, beyond the
four-tool checklist: LangGraph's own workflow state is checkpointed into
CockroachDB after every graph node via `AsyncCockroachDBSaver` (so a crashed
container or a scaled-out AgentCore replica resumes an investigation exactly
where it left off), and every completed conversational turn is written to a
separate, human-readable `message_store` table via
`CockroachDBChatMessageHistory` — the durable, queryable audit trail a real
market-surveillance workflow actually needs for compliance, independent of
LangGraph's own internal checkpoint format.

**Amazon Bedrock AgentCore is the only AWS service used, and only for
hosting.** `api.py` wraps the LangGraph workflow in a `BedrockAgentCoreApp`
entrypoint; `deployment/` builds the container, pushes it to ECR, and
provisions the AgentCore runtime and endpoint via `boto3`. Model reasoning
never touches Bedrock — every Strands agent calls Anthropic's API directly
through an `AnthropicModel`. This isn't just an architectural claim: the
deployment IAM policy (`deployment/permissions-policy.json`) carries no
`bedrock:InvokeModel` permission at all, so the system is structurally
incapable of routing inference through Bedrock even by accident.

---

## Pre-existing code or work incorporated into the Project

*(Paste this into the disclosure field.)*

**One piece of pre-existing code was incorporated: AWS's own sample
repository for this domain.** This project's market-surveillance agent
personas, their prompts, the mock trading-data catalog, and report schemas
originate from AWS's public sample,
["Market Surveillance Agent with LangGraph and Strands on AgentCore"](https://aws.amazon.com/blogs/machine-learning/market-surveillance-agent-with-langgraph-and-strands-on-agentcore/)
(repository `aws-samples/sample-market-surveillance-langgraph-strands-agentcore`,
licensed MIT-0 per its own README). That sample was used as a reference
starting point before any hackathon-specific development began, and this
project explicitly forks its domain layer.

Specifically reused/adapted from that sample:
- Four specialist agent personas — `security_monitor`, `broker_monitor`,
  `risk_monitor`, `intel_analyst` — and their system prompts
- The mock trading-data catalog and report schemas (`get_report_list`,
  `get_report_schema`, `run_report` and the underlying mock datasets)
- The general LangGraph `StateGraph` + orchestrator-routing pattern

Everything else was built during the submission period, and is the part
actually being judged:
- The entire CockroachDB memory layer — the LangGraph checkpointer
  (`AsyncCockroachDBSaver`), the durable audit trail
  (`CockroachDBChatMessageHistory`), and long-term semantic case memory
  (`AsyncCockroachDBVectorStore` + a C-SPANN distributed vector index) —
  none of which existed in the original sample, which used AgentCore Memory
  instead
- Swapping model inference from Bedrock-hosted models to Anthropic's API
  called directly through Strands, and reworking the IAM policy accordingly
- Four new specialist agents — `memory_ops` (CockroachDB Cloud MCP Server
  integration), `compliance_officer`, `case_triage`, `audit_reviewer` —
  each putting a different CockroachDB memory component directly in an
  agent's hands as a tool call
- The FastAPI backend (`server/`) and the entire React + Vite + Tailwind UI
  (`web/`) — Chat and Dashboard views, the Vector Memory Map, the Time
  Travel checkpoint viewer, the live agent pipeline graph, explainable
  triage citations — none of which existed in the original sample, which
  shipped only a Streamlit UI
- `scripts/provision_cluster.sh` (ccloud CLI provisioning) and the
  CockroachDB-specific portions of the deployment scripts

**Standard tools used, as explicitly permitted by the rules:** LangGraph,
the Strands Agents SDK, FastAPI, React/Vite/Tailwind CSS, `langchain-cockroachdb`,
`psycopg`, `fastembed`, `boto3`/the AWS SDK, and Anthropic's Python SDK —
all installed as ordinary open-source dependencies via `pip`/`npm`, used
unmodified. This project was built with the assistance of Claude Code
(Anthropic's AI coding assistant).

---

## Which AI tools have you leveraged while working on this project?

*(Paste this into the disclosure field.)*

**Claude Code** (Anthropic's agentic CLI coding assistant) was the AI tool
used throughout this project's development — end-to-end implementation of
the CockroachDB memory layer, debugging (including finding and fixing the
silently-broken vector-recall path described above), running and verifying
commands against a real CockroachDB cluster, writing the FastAPI and React
layers, and drafting this submission's documentation.

One distinction worth being precise about for this disclosure: that's
separate from the fact that the *deployed application itself* calls
Anthropic's Claude models at runtime, through the Strands Agents SDK, as
part of its own product behavior — every specialist agent's reasoning is a
live call to Anthropic's API. That's part of what was built, a product
architecture choice already documented in the sections above, not a tool
"leveraged while working on" the project in the sense this question asks
about.

No other AI coding assistants or code-generation tools were used.

---

## Testing credentials or instructions for your functional demo app

*(Paste this into the "testing credentials / instructions" field.)*

**No login or account is required to use the app.** Market Memory Mesh
Agents has no multi-tenant user system — there's nothing to sign up for and
no per-user credentials to hand out.

Two ways to test it:

1. **Locally, in a few minutes (recommended for judging):**
   ```bash
   git clone https://github.com/akashtalole/MemoryMesh-Agents.git
   cd MemoryMesh-Agents
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # fill in ANTHROPIC_API_KEY + COCKROACHDB_URL
   make init-memory && make seed-memory
   make dev
   ```
   Then open **http://localhost:5173** for the full functional demo, with
   zero AWS involved. Full walkthrough: `docs/SETUP_GUIDE.md`. You'll need
   your own Anthropic API key (free to create at console.anthropic.com) and
   a CockroachDB cluster (a free CockroachDB Cloud cluster takes under a
   minute at cockroachlabs.cloud, or run `cockroach demo` locally) — these
   are standard "bring your own key" requirements, the same as any project
   that calls a third-party API, not app-level login credentials.

2. **Hosted AWS AgentCore demo, if a live link is included with this
   submission:** that deployment sits behind a single shared access
   password so it can stay publicly reachable during judging without
   risking uncontrolled Anthropic API spend from open traffic — it's a
   cost-control gate added for judging, not a product feature. The password
   is provided separately, alongside the demo link, rather than published
   in this public repository. If the link loads straight into the app with
   no password prompt, the gate simply wasn't enabled for that deployment
   and no credentials are needed.

---

## Suggested hashtags

*(For sharing the submission on social media — not a Devpost form field.
Devpost's submission checklist typically wants a post on X/Twitter or
LinkedIn tagging the hackathon; these cover the hackathon/sponsor tags plus
the project's actual tech stack.)*

**Hackathon / sponsor tags:**
```
#CockroachDBHackathon #CockroachDB #AWS #BuildOnCockroachDB #DevPost
```

**Tech / project tags:**
```
#AgentCore #AmazonBedrock #Anthropic #ClaudeAI #LangGraph #AIAgents
#MultiAgentSystems #VectorSearch #DistributedSQL #GenAI #MachineLearning
#BuildInPublic
```

**All-in-one line (trim to fit your platform's limit):**
```
#CockroachDBHackathon #CockroachDB #AWS #AgentCore #Anthropic #ClaudeAI #LangGraph #AIAgents #VectorSearch #GenAI
```

Before posting, double check the exact official tag Devpost/CockroachDB
asks for in the hackathon rules page (hackathons sometimes require a
specific spelling, e.g. `#CockroachDBAWSHackathon`) and use that verbatim
alongside these.
