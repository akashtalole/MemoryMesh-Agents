import { useState } from "react";
import { agentColor, type AgentUsage } from "../../types";
import { AGENT_LABELS } from "../../types";
import EmptyChart from "./EmptyChart";

interface Props {
  data: AgentUsage[];
}

/**
 * Horizontal bar chart, one row per agent. Mark spec: bar ≤24px thick,
 * square at the baseline (left), 4px rounded at the data-end (right); a
 * direct value label rides every bar rather than relying on color alone,
 * since the fixed categorical palette has one adjacent pair in the CVD
 * warn band. Hover reveals a per-row tooltip.
 */
export default function BarChart({ data }: Props) {
  const [hover, setHover] = useState<number | null>(null);

  if (data.length === 0) {
    return <EmptyChart label="No agent activity recorded yet — ask a question to get started." />;
  }

  const max = Math.max(1, ...data.map((d) => d.count));

  return (
    <div className="flex flex-col gap-2.5">
      {data.map((d, i) => {
        const pct = Math.max((d.count / max) * 100, 4);
        // Color keys off the agent's fixed identity slot, never its rank in
        // this count-sorted list — otherwise an agent's color would change
        // every time the ranking shifts between polls.
        const color = agentColor(d.agent);
        const label = AGENT_LABELS[d.agent] ?? d.agent;
        const isHover = hover === i;

        return (
          <div
            key={d.agent}
            className={`relative flex items-center gap-3 rounded-md px-1 py-1 transition-colors ${
              isHover ? "bg-ink-800/60" : ""
            }`}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover((h) => (h === i ? null : h))}
          >
            <span className="w-32 shrink-0 truncate text-[11px] text-slate-400">{label}</span>
            <div className="h-3.5 flex-1 rounded-sm bg-ink-800">
              <div
                className="h-3.5 rounded-r-[4px] transition-[width] duration-300 ease-out"
                style={{ width: `${pct}%`, backgroundColor: color }}
              />
            </div>
            <span className="w-6 shrink-0 text-right text-[11px] tabular-nums text-slate-300">{d.count}</span>

            {isHover && (
              <div className="pointer-events-none absolute right-1 top-full z-10 mt-1 whitespace-nowrap rounded-md border border-ink-600 bg-ink-850 px-2 py-1 text-[11px] text-slate-200 shadow-lg">
                <span className="font-medium">{label}</span>
                <span className="text-slate-500"> — {d.count} case{d.count === 1 ? "" : "s"}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
