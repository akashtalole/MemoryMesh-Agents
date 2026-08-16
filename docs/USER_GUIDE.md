# MemoryMesh Agent — User Guide

How to actually use MemoryMesh Agent once it's running. If you haven't set
it up yet, start with the [Setup Guide](SETUP_GUIDE.md).

MemoryMesh Agent is a multi-agent market-surveillance assistant. You ask it
questions in plain English; a team of specialist agents investigates,
reasons over the results, and answers — and everything they learn is
written into CockroachDB so future questions benefit from it.

## The app shell

Open the app (`http://localhost:5173` in local dev) and you'll see a left
nav rail with two views: **Chat** and **Dashboard**. The header always shows
two status badges:

- **Local** (amber) or **AgentCore** (indigo) — which backend is answering
  your questions right now
- **CockroachDB connected** (green) or **CockroachDB offline** (red) — live
  connectivity to the memory layer

If the CockroachDB badge is ever red, nothing else in the app will work
correctly — see the Setup Guide's troubleshooting section.

## Chat view

This is the main view: a conversation with the multi-agent system, plus a
memory sidebar on the right.

### Asking a question

Type a question into the composer at the bottom and send it. A few things
happen, visibly:

1. The system checks CockroachDB's long-term case memory for anything
   similar it has investigated before (you won't see a separate step for
   this — it happens before the answer starts streaming, and it changes
   *what* the agents say if a related case exists).
2. The right specialist agent (or agents) run and stream their answer back
   token by token.
3. Under the assistant's message, a compact **agent pipeline graph**
   appears — a small node graph showing exactly which agents ran and how
   many tool calls each one made, built live from the same event stream as
   the answer itself. This is your window into "who actually answered this"
   without reading raw logs.
4. If an agent's investigation returns citations (see **Triage citations**
   below), they render as clickable chips under the pipeline.

### Which agent handles what

You don't pick an agent — the orchestrator routes your question based on
its content. Rough guide to what triggers what:

| Ask about... | Routes to |
|---|---|
| Trading activity for one security, one day | `security_monitor` |
| One security across multiple days | `broker_monitor` |
| Broker activity on a given day | `risk_monitor` |
| External market news/context | `intel_analyst` |
| **The system's own memory** — case counts, past investigations, cluster health | `memory_ops` |
| Whether a finding is a compliance issue | `compliance_officer` |
| How urgent an investigation is | `case_triage` |
| A summary of this session's history | `audit_reviewer` |

A single question can route to more than one agent — the pipeline graph
shows you exactly which ones ran.

### Example queries to try

```text
# A first investigation — this writes a new case into memory
What was the trading activity for AAPL on March 15, 2024 and which brokers were most active?

# Ask something similar later, in a new session — watch the answer's
# context include a recalled prior case
Which brokers were most active trading AAPL in mid-March 2024?

# Memory introspection — routes to memory_ops, which queries CockroachDB
# live via the Cloud Managed MCP Server
How many past investigations do we have stored, and have we looked at broker risk on MSFT before?

# Multi-agent
Analyze MSFT's price movement and broker risk scores between March 10-15, 2024, and check for any related market news.

# Compliance + triage — case_triage explicitly queries case memory to set priority
Is ALPHA_CAPITAL's AAPL trading on March 15, 2024 a compliance issue, and how urgent is it?

# Audit — reads message_store directly, not the model's own recollection
Give me an audit summary of everything asked and answered in this session.
```

### Triage citations

When `case_triage` runs, it calls `recall_similar_investigations` against
the vector index itself (a second, agent-driven path into the same memory
the automatic recall step uses). If it finds matches, they show up as small
citation chips — case ID and similarity score — directly under the pipeline
graph, so you can see exactly which past cases informed the urgency
assessment instead of taking the model's word for it.

### History — replaying a session's checkpoints

Click **History** in the header (next to your session ID) to open the
**time-travel** view: a scrubber over every checkpoint LangGraph has saved
for the current session, in order. Each step shows the actual workflow
state at that point — which node had just run, what it had produced.
Because `AsyncCockroachDBSaver` already persists a checkpoint after every
node, this view costs nothing extra to build — it's a live read of state
that was already being saved.

### Memory sidebar

The right-hand panel (desktop only) shows three live counters — **Cases**,
**Turns**, **Sessions** — polled every few seconds directly from
CockroachDB, plus a short list of recent cases. Watch the case count tick
up as you chat; each finished investigation writes itself back into
`case_memory`, so the count is real accumulated history, not a per-session
tally.

### New session

Click **New session** to start a fresh conversation. Past sessions aren't
deleted — they're still in `message_store` and queryable by
`audit_reviewer`, and any cases they produced are still in long-term memory
for future recall.

## Dashboard view

Switch to **Dashboard** in the nav rail for an operational view of the same
CockroachDB tables the agents use — everything here is a live read, not a
mock.

- **Stat tiles** — cases, turns, sessions, and system health at a glance.
- **Agent activity chart** — a bar chart of tool calls per agent, colored
  consistently (an agent always gets the same color, regardless of how the
  bars are currently sorted — earlier versions of this chart had a bug
  where colors were assigned by sorted rank and would visibly shift between
  polls; that's fixed).
- **Cases-per-day chart** — a time series of investigation volume over the
  last 14 days.
- **Vector Memory Map** — every case's embedding, projected to 2D and
  plotted as a point cloud. Type a query into its search box and it runs
  the *same* similarity search the agents use internally, plots your query
  alongside its real nearest neighbors on the same projection, and lists
  the ranked matches below. This is the distributed vector index made
  visible and queryable, not just a number.
- **Recent cases table** — the latest investigations, most recent first.
- **System health** — backend mode and CockroachDB connectivity, same
  badges as the header.

## Command-line alternative

Prefer a terminal over the browser? `python scripts/chat_cli.py` runs the
exact same LangGraph workflow with no HTTP layer at all — useful for
scripting or quick checks.

## Tips

- Ask a near-duplicate question in a *different* session to see recall
  working — the giveaway is the answer referencing a prior finding you
  never mentioned in the current conversation.
- If you want the Dashboard to have something to show immediately on a
  fresh cluster, run `make seed-memory` before you start chatting (see the
  Setup Guide).
- The MCP-powered `memory_ops` agent only works if `COCKROACHDB_MCP_API_KEY`
  is set; without it, questions about the memory cluster itself will get a
  graceful "can't introspect the live cluster" answer instead of an error.
