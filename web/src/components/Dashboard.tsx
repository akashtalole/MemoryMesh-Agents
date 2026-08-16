import { useEffect, useState, type ReactNode } from "react";
import { Activity, Boxes, Brain, Database, MessagesSquare, Scan, Users } from "lucide-react";
import { fetchAgentUsage, fetchCasesTimeseries, fetchMemoryStats, fetchRecentCases } from "../lib/api";
import type { AgentUsage, HealthInfo, MemoryStats, RecentCase, TimeseriesPoint } from "../types";
import { AGENT_LABELS, STATUS_COLORS } from "../types";
import StatTile from "./StatTile";
import { Badge } from "./Header";
import BarChart from "./charts/BarChart";
import TimeSeriesChart from "./charts/TimeSeriesChart";
import MemoryMap from "./MemoryMap";

const POLL_MS = 10000;

export default function Dashboard({ health }: { health: HealthInfo | null }) {
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [cases, setCases] = useState<RecentCase[]>([]);
  const [usage, setUsage] = useState<AgentUsage[]>([]);
  const [series, setSeries] = useState<TimeseriesPoint[]>([]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const [s, c, u, t] = await Promise.all([
          fetchMemoryStats(),
          fetchRecentCases(10),
          fetchAgentUsage(),
          fetchCasesTimeseries(14),
        ]);
        if (!cancelled) {
          setStats(s);
          setCases(c);
          setUsage(u);
          setSeries(t);
        }
      } catch {
        /* keep last known values, don't blank the dashboard on a transient failure */
      }
    };
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const trend = series.map((p) => p.count);

  return (
    <div className="scrollbar-thin flex-1 overflow-y-auto p-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        {/* Stat tiles */}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatTile
            label="Cases in memory"
            value={stats?.cases ?? "–"}
            icon={<Brain size={16} />}
            trend={trend.length > 1 ? trend : undefined}
          />
          <StatTile label="Conversation turns" value={stats?.turns ?? "–"} icon={<MessagesSquare size={16} />} />
          <StatTile label="Sessions" value={stats?.sessions ?? "–"} icon={<Users size={16} />} />
          <StatTile
            label="CockroachDB"
            value={stats?.connected ? "Connected" : "Offline"}
            icon={<Database size={16} />}
            toneColor={stats?.connected ? STATUS_COLORS.good : STATUS_COLORS.critical}
          />
        </div>

        {/* Vector Memory Map */}
        <Card
          title="Vector memory map"
          subtitle="Every case embedding, projected to 2D — search to see where a new query would land"
          icon={<Scan size={14} />}
        >
          <MemoryMap />
        </Card>

        {/* Charts */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card title="Agent activity" subtitle="Cases each agent has participated in" icon={<Activity size={14} />}>
            <BarChart data={usage} />
          </Card>
          <Card title="Cases recorded per day" subtitle="Last 14 days" icon={<Boxes size={14} />}>
            <TimeSeriesChart data={series} />
          </Card>
        </div>

        {/* Recent cases table + system health */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <Card title="Recent investigations" subtitle="Latest cases written to long-term memory" icon={<Brain size={14} />}>
              <CasesTable cases={cases} />
            </Card>
          </div>
          <Card title="System health" subtitle="Backend + memory connection" icon={<Database size={14} />}>
            <SystemHealth health={health} />
          </Card>
        </div>
      </div>
    </div>
  );
}

function Card({
  title,
  subtitle,
  icon,
  children,
}: {
  title: string;
  subtitle: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-ink-700 bg-ink-900/60 p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-slate-500">{icon}</span>
        <div>
          <h3 className="text-xs font-semibold text-slate-200">{title}</h3>
          <p className="text-[11px] text-slate-600">{subtitle}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

function CasesTable({ cases }: { cases: RecentCase[] }) {
  if (cases.length === 0) {
    return <p className="py-6 text-center text-xs text-slate-600">No investigations recorded yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[11px]">
        <thead>
          <tr className="text-slate-600">
            <th className="pb-2 pr-3 font-medium">Query</th>
            <th className="pb-2 pr-3 font-medium">Agents</th>
            <th className="pb-2 font-medium">Recorded</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.case_id ?? c.query} className="border-t border-ink-700/60">
              <td className="max-w-[280px] truncate py-2 pr-3 text-slate-300" title={c.query ?? ""}>
                {c.query ?? "—"}
              </td>
              <td className="py-2 pr-3">
                <div className="flex flex-wrap gap-1">
                  {parseAgents(c.agents).map((a) => (
                    <span key={a} className="rounded-full bg-ink-800 px-1.5 py-0.5 text-[10px] text-slate-400">
                      {AGENT_LABELS[a] ?? a}
                    </span>
                  ))}
                </div>
              </td>
              <td className="py-2 tabular-nums text-slate-500">{formatTime(c.recorded_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SystemHealth({ health }: { health: HealthInfo | null }) {
  if (!health) {
    return <p className="text-xs text-slate-600">Loading…</p>;
  }

  return (
    <dl className="flex flex-col gap-3 text-xs">
      <Row label="Backend mode">
        <Badge
          icon={<Activity size={11} />}
          label={health.backend_mode === "agentcore" ? "AgentCore" : "Local"}
          tone={health.backend_mode === "agentcore" ? "indigo" : "amber"}
        />
      </Row>
      <Row label="CockroachDB">
        <Badge
          icon={<Database size={11} />}
          label={health.cockroachdb_connected ? "Connected" : "Offline"}
          tone={health.cockroachdb_connected ? "emerald" : "rose"}
        />
      </Row>
      <Row label="Region">
        <span className="text-slate-300">{health.region}</span>
      </Row>
      {health.runtime_arn && (
        <Row label="Runtime ARN">
          <span className="truncate font-mono text-[10px] text-slate-400" title={health.runtime_arn}>
            {health.runtime_arn}
          </span>
        </Row>
      )}
      {health.cockroachdb_error && (
        <p className="rounded-md bg-rose-500/10 px-2 py-1.5 text-[11px] text-rose-400">
          {health.cockroachdb_error}
        </p>
      )}
    </dl>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-slate-600">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function parseAgents(agents: string | null): string[] {
  if (!agents) return [];
  try {
    const parsed = JSON.parse(agents);
    if (Array.isArray(parsed)) return parsed;
  } catch {
    /* not JSON */
  }
  return [agents];
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}
