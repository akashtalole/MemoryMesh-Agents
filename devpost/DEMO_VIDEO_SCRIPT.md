# 3-Minute Demo Video — Script & Shot Outline

Target runtime: **2:45–3:00**. Pace assumes ~140 words/minute narration.
Record the UI at 1440×900 or larger; zoom in during code cutaways so text is
legible on a phone screen.

## Before you record — prep checklist

- [ ] `make init-memory` run against a clean cluster (empty tables, so the
      case count starts at 0 on camera — the "watch it grow" moment only
      lands if it visibly starts from zero)
- [ ] `make dev` running, browser open to the Chat view, window sized so
      the memory sidebar is visible
- [ ] Have the four sample queries below typed out somewhere you can
      paste from, so there's no on-camera typos/typing lag
- [ ] Terminal window ready with `deployment/permissions-policy.json` open
      (for the 2:15 cutaway) and `src/memory/case_memory.py` open (for the
      2:05 cutaway)
- [ ] Know your two demo cases before you record: AAPL/VERTEX_SECURITIES
      (first ask) and a paraphrase of it (second ask) — using the exact
      pairs below means the recall match is guaranteed, not lucky

---

## Scene-by-scene script

### 0:00–0:15 — Cold open: the problem (talking head or voiceover over a blank/dark screen)

**Narration:**
> "Most multi-agent demos have amnesia. Ask them the same question twice
> and they've got no idea they've seen it before — because 'memory' is
> just a chat buffer that resets. In a compliance domain like market
> surveillance, that's not a quirk, it's a liability. This is Market
> Memory Mesh Agents — a surveillance team whose memory is CockroachDB,
> not RAM."

**On screen:** Title card or your face. No UI yet — this is the hook.

---

### 0:15–0:40 — Architecture in 25 seconds

**Narration:**
> "LangGraph orchestrates eight specialist agents, reasoning through
> Anthropic's API via Strands. Every layer of memory — workflow
> checkpoints, a durable audit log, and long-term semantic case memory —
> lives in one CockroachDB cluster. The only AWS service in the stack is
> Bedrock AgentCore, and it's used for exactly one thing: hosting the
> runtime. Model inference never touches Bedrock."

**On screen:** Quick cut to the architecture diagram from the README
(screenshot or scroll), or a simple on-screen graphic: Chat UI → FastAPI →
CockroachDB (three labeled stores) + AgentCore (one label: "hosting only").

---

### 0:40–1:00 — First question: an ordinary investigation

**Narration:**
> "Let's ask it something."

**On screen:** Type/paste into the Chat composer:
```
What was the trading activity for AAPL on March 15, 2024 and which brokers were most active?
```
Let it stream. Show the **live agent pipeline** graph lighting up under the
message as agents run. Briefly point at the **memory sidebar** — case count
is 0 → about to become 1.

**Narration (while it streams, softer/faster):**
> "It's fanning out to the right specialists, streaming its answer, and
> when it's done, that investigation gets embedded and written straight
> into CockroachDB's case memory. Watch the sidebar."

**On screen:** Case count ticks from 0 to 1 the moment synthesis finishes.

---

### 1:00–1:35 — Second question: recall in action (the money shot)

**Narration:**
> "Now — new session, different phrasing, days of 'elapsed time' as far
> as the app's concerned."

**On screen:** Click **New session**. Paste:
```
Which brokers were most active trading AAPL in mid-March 2024?
```

**Narration:**
> "Before the orchestrator even decides how to route this, it's already
> asked CockroachDB's distributed vector index: have we seen something
> like this before? It has — and that recalled context shapes the
> answer you're about to see."

**On screen:** Let it stream; if the UI surfaces recalled-case context or
citations, pause and point at them explicitly. Sidebar case count is still
1 here (recall, not a new case) — call that out verbally so it's not
confusing: *"count stays at 1 — this was a recall, not a new
investigation."*

---

### 1:35–2:00 — The memory made visible (Dashboard)

**Narration:**
> "That vector index isn't just plumbing — you can see it."

**On screen:** Click into **Dashboard**. Show the **Vector Memory Map**:
type a partial query into its search box (e.g. `AAPL broker risk`), watch
the point cloud highlight the nearest neighbors and the ranked list update
live.

**Narration:**
> "Every case embedding, projected live, searchable in real time — the
> same recall function the agents use internally, just made visible."

**On screen:** Quick cut to the **Time Travel** scrubber (open History from
a Chat session): drag the slider across a few checkpoint steps.

**Narration (fast):**
> "And because LangGraph checkpoints every node into CockroachDB, you
> can scrub through exactly how any investigation got its answer, step
> by step."

---

### 2:00–2:20 — The agent that reads its own database

**Narration:**
> "One more agent worth seeing."

**On screen:** Back to Chat, paste:
```
How many past investigations do we have stored, and have we looked at broker risk on MSFT before?
```
Let it route and answer.

**Narration:**
> "That routed to `memory_ops` — an agent wired to CockroachDB's own
> Cloud Managed MCP Server. It isn't guessing a count. It's querying the
> live cluster, read-only, through the same managed server CockroachDB
> ships."

---

### 2:20–2:40 — Under the hood: what makes this real (fast code cutaways)

**Narration:**
> "Under the hood: CockroachDB is the only system of record — no Redis,
> no separate vector database. And AWS stays exactly where it belongs."

**On screen:** Two-second cuts, each with the relevant line highlighted:
1. `src/memory/case_memory.py` — the `AsyncCockroachDBVectorStore` +
   `CSPANNIndex` construction.
2. `deployment/permissions-policy.json` — scroll to show there is no
   `bedrock:InvokeModel` anywhere in the policy.

**Narration (over the second cutaway):**
> "No Bedrock inference permission, anywhere in this policy — AgentCore
> hosts the container. That's it."

---

### 2:40–2:55 — Close

**Narration:**
> "Market Memory Mesh Agents: a multi-agent system that doesn't just
> answer your question — it remembers doing it, forever, in CockroachDB.
> Built for the CockroachDB × AWS Hackathon."

**On screen:** Return to Chat view, memory sidebar visible with case count
> 1, then title card / GitHub repo URL / Devpost link.

---

## Optional B-roll (only if you have room under 3:00)

- The `SEV`/priority badge from a `compliance_officer` or `case_triage`
  routed question, to show the CLEAR/FLAGGED verdict and urgency scoring.
- `audit_reviewer` answering *"Give me an audit summary of everything asked
  and answered in this session"* — ties back to the durable
  `message_store` audit table.
- A terminal split-screen of `make deploy` succeeding, if you have a real
  AgentCore runtime deployed and want to prove the AWS path isn't just
  scripts that were never run.

## Timing cheat sheet

| Segment | Duration | Running total |
|---|---|---|
| Cold open | 0:15 | 0:15 |
| Architecture | 0:25 | 0:40 |
| First question | 0:20 | 1:00 |
| Recall (money shot) | 0:35 | 1:35 |
| Dashboard: memory made visible | 0:25 | 2:00 |
| memory_ops / MCP | 0:20 | 2:20 |
| Code cutaways | 0:20 | 2:40 |
| Close | 0:15 | 2:55 |
