import { Fragment, useState } from "react";
import { ChevronDown, Quote, Wrench } from "lucide-react";
import { AGENT_INITIALS, AGENT_LABELS, agentColor, type TraceEntry } from "../types";

interface Citation {
  case_id: string;
  query: string;
  score: number;
}

interface PipelineNode {
  agent: string;
  status: "active" | "done";
  toolCount: number;
}

function buildPipeline(trace: TraceEntry[]): PipelineNode[] {
  const order: string[] = [];
  const lastStatus: Record<string, string> = {};
  const toolCounts: Record<string, number> = {};

  for (const t of trace) {
    if (t.kind === "agent") {
      if (!order.includes(t.agent)) order.push(t.agent);
      lastStatus[t.agent] = t.status;
    } else if (t.kind === "tool" && t.status === "tool_result") {
      toolCounts[t.agent] = (toolCounts[t.agent] ?? 0) + 1;
    }
  }

  return order.map((agent) => ({
    agent,
    status: lastStatus[agent] === "end" ? "done" : "active",
    toolCount: toolCounts[agent] ?? 0,
  }));
}

/** Parses a recall_similar_investigations tool result into citation chips —
 * the case memory search results an agent actually reasoned over. */
function parseCitations(detail?: string): Citation[] {
  if (!detail) return [];
  try {
    const parsed = JSON.parse(detail);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((m) => m && typeof m === "object" && m.case_id)
      .map((m) => ({ case_id: String(m.case_id), query: String(m.query ?? ""), score: Number(m.score ?? 0) }));
  } catch {
    return [];
  }
}

export default function AgentTrace({ trace }: { trace: TraceEntry[] }) {
  const [open, setOpen] = useState(false);
  if (trace.length === 0) return null;

  const nodes = buildPipeline(trace);
  const toolEntries = trace.filter((t) => t.kind === "tool" && t.status === "tool_result");
  const citationEntries = toolEntries
    .map((t) => ({ agent: t.agent, label: t.label, citations: parseCitations(t.detail) }))
    .filter((c) => c.citations.length > 0);

  return (
    <div className="mt-2 rounded-lg border border-ink-700 bg-ink-900/50 px-3 py-2">
      {/* Live/completed pipeline */}
      <div className="flex items-center gap-1 overflow-x-auto">
        {nodes.map((n, i) => (
          <Fragment key={n.agent}>
            {i > 0 && <div className="h-px w-3 shrink-0 bg-ink-600" />}
            <div className="flex flex-col items-center gap-1" title={AGENT_LABELS[n.agent] ?? n.agent}>
              <span
                className={`relative flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[9px] font-bold text-ink-950 ${
                  n.status === "active" ? "animate-pulse" : ""
                }`}
                style={{ backgroundColor: agentColor(n.agent) }}
              >
                {AGENT_INITIALS[n.agent] ?? n.agent.slice(0, 2).toUpperCase()}
                {n.toolCount > 0 && (
                  <span className="absolute -bottom-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-ink-900 text-[8px] text-amber-400 ring-1 ring-ink-700">
                    {n.toolCount}
                  </span>
                )}
              </span>
              <span className="max-w-[56px] truncate text-[9px] text-slate-500">
                {(AGENT_LABELS[n.agent] ?? n.agent).split(" ")[0]}
              </span>
            </div>
          </Fragment>
        ))}
      </div>

      {/* Citations surfaced from any recall_similar_investigations tool call */}
      {citationEntries.length > 0 && (
        <div className="mt-2 flex flex-col gap-1.5 border-t border-ink-700 pt-2">
          {citationEntries.map(({ agent, citations }) => (
            <div key={agent} className="flex flex-wrap items-center gap-1.5">
              <span className="flex items-center gap-1 text-[10px] text-slate-500">
                <Quote size={10} />
                {AGENT_LABELS[agent] ?? agent} cited:
              </span>
              {citations.map((c) => (
                <span
                  key={c.case_id}
                  title={c.query}
                  className="cursor-help rounded-full border border-ink-600 bg-ink-800 px-2 py-0.5 text-[10px] text-slate-300"
                >
                  {c.query.length > 28 ? c.query.slice(0, 28) + "…" : c.query}
                  <span className="ml-1 text-slate-500">{c.score.toFixed(2)}</span>
                </span>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Full detail toggle */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="mt-2 flex w-full items-center justify-between gap-2 border-t border-ink-700 pt-2 text-left text-[11px] text-slate-500 transition hover:text-slate-300"
      >
        <span>
          {nodes.length} agent{nodes.length === 1 ? "" : "s"} · {toolEntries.length} tool call
          {toolEntries.length === 1 ? "" : "s"}
        </span>
        <ChevronDown size={13} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <ol className="mt-1.5 flex flex-col gap-1">
          {trace.map((entry) => (
            <li key={entry.key} className="flex items-start gap-2 text-[11px] text-slate-400">
              <Wrench
                size={11}
                className={`mt-0.5 ${entry.kind === "tool" ? "text-amber-500" : "text-transparent"}`}
              />
              <span>
                <span className="font-medium text-slate-300">
                  {entry.kind === "agent" ? AGENT_LABELS[entry.agent] ?? entry.agent : entry.label}
                </span>{" "}
                <span className="text-slate-600">
                  {entry.kind === "agent"
                    ? entry.status === "end"
                      ? "finished"
                      : "started"
                    : `(${AGENT_LABELS[entry.agent] ?? entry.agent}) — ${entry.status}`}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
