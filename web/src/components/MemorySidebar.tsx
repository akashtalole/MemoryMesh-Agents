import { useEffect, useState, type ReactNode } from "react";
import { Brain, MessagesSquare, RadioTower, Users } from "lucide-react";
import { fetchMemoryStats, fetchRecentCases } from "../lib/api";
import type { MemoryStats, RecentCase } from "../types";

const POLL_MS = 6000;

export default function MemorySidebar() {
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [cases, setCases] = useState<RecentCase[]>([]);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const [s, c] = await Promise.all([fetchMemoryStats(), fetchRecentCases(6)]);
        if (!cancelled) {
          setStats(s);
          setCases(c);
        }
      } catch {
        if (!cancelled) setStats({ connected: false, cases: 0, turns: 0, sessions: 0 });
      }
    };

    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <aside className="hidden w-80 shrink-0 flex-col gap-4 overflow-y-auto border-l border-ink-700 bg-ink-900/60 p-4 lg:flex scrollbar-thin">
      <div>
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <Brain size={13} />
          CockroachDB memory
        </div>
        <div className="grid grid-cols-3 gap-2">
          <StatCard icon={<Brain size={14} />} label="Cases" value={stats?.cases} />
          <StatCard icon={<MessagesSquare size={14} />} label="Turns" value={stats?.turns} />
          <StatCard icon={<Users size={14} />} label="Sessions" value={stats?.sessions} />
        </div>
        {stats && !stats.connected && (
          <p className="mt-2 text-[11px] text-rose-400">
            Not connected — check COCKROACHDB_URL on the API server.
          </p>
        )}
      </div>

      <div className="flex-1">
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <RadioTower size={13} />
          Recent cases
        </div>
        {cases.length === 0 ? (
          <p className="text-xs text-slate-600">
            No investigations recorded yet — ask a question, or run{" "}
            <code className="text-emerald-400">make seed-memory</code>.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {cases.map((c) => (
              <li
                key={c.case_id ?? c.query}
                className="rounded-lg border border-ink-700 bg-ink-850 px-3 py-2 text-xs text-slate-300"
              >
                <p className="line-clamp-2 text-slate-200">{c.query ?? "—"}</p>
                <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500">
                  <span>{formatAgents(c.agents)}</span>
                  <span>{formatTime(c.recorded_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="text-[11px] leading-relaxed text-slate-600">
        Every case here is embedded and stored via a distributed C-SPANN
        vector index — new questions are matched against this table before
        the orchestrator even routes them.
      </p>
    </aside>
  );
}

function StatCard({ icon, label, value }: { icon: ReactNode; label: string; value?: number }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-850 px-2.5 py-2">
      <div className="flex items-center gap-1.5 text-slate-500">
        {icon}
        <span className="text-[10px] uppercase tracking-wide">{label}</span>
      </div>
      <p className="mt-1 text-lg font-semibold text-slate-100">{value ?? "–"}</p>
    </div>
  );
}

function formatAgents(agents: string | null): string {
  if (!agents) return "";
  try {
    const parsed = JSON.parse(agents);
    if (Array.isArray(parsed)) return parsed.join(", ");
  } catch {
    /* not JSON, fall through */
  }
  return agents;
}

function formatTime(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}
