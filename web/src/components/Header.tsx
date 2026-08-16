import type { ReactNode } from "react";
import { Clock, Database, RotateCcw, Server } from "lucide-react";
import type { HealthInfo } from "../types";

interface Props {
  title: string;
  subtitle: string;
  health: HealthInfo | null;
  sessionId?: string | null;
  onNewSession?: () => void;
  onOpenHistory?: () => void;
}

export default function Header({ title, subtitle, health, sessionId, onNewSession, onOpenHistory }: Props) {
  return (
    <header className="flex items-center justify-between border-b border-ink-700 bg-ink-900/80 px-5 py-3 backdrop-blur">
      <div>
        <h1 className="text-sm font-semibold leading-tight text-slate-50">{title}</h1>
        <p className="text-xs leading-tight text-slate-500">{subtitle}</p>
      </div>

      <div className="flex items-center gap-3">
        {health && (
          <div className="hidden items-center gap-3 sm:flex">
            <Badge
              icon={<Server size={12} />}
              label={health.backend_mode === "agentcore" ? "AgentCore" : "Local"}
              tone={health.backend_mode === "agentcore" ? "indigo" : "amber"}
            />
            <Badge
              icon={<Database size={12} />}
              label={health.cockroachdb_connected ? "CockroachDB connected" : "CockroachDB offline"}
              tone={health.cockroachdb_connected ? "emerald" : "rose"}
            />
          </div>
        )}
        {sessionId && (
          <span className="hidden font-mono text-[11px] text-slate-600 md:inline">
            session {sessionId.slice(0, 8)}
          </span>
        )}
        {onOpenHistory && sessionId && (
          <button
            onClick={onOpenHistory}
            title="Time travel through this session's checkpoints"
            className="flex items-center gap-1.5 rounded-lg border border-ink-600 bg-ink-800 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-ink-600 hover:bg-ink-700 hover:text-slate-100"
          >
            <Clock size={13} />
            History
          </button>
        )}
        {onNewSession && (
          <button
            onClick={onNewSession}
            className="flex items-center gap-1.5 rounded-lg border border-ink-600 bg-ink-800 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-ink-600 hover:bg-ink-700 hover:text-slate-100"
          >
            <RotateCcw size={13} />
            New session
          </button>
        )}
      </div>
    </header>
  );
}

export function Badge({ icon, label, tone }: { icon: ReactNode; label: string; tone: "emerald" | "rose" | "indigo" | "amber" }) {
  const tones: Record<string, string> = {
    emerald: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    rose: "bg-rose-500/10 text-rose-400 border-rose-500/20",
    indigo: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
    amber: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  };
  return (
    <span className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${tones[tone]}`}>
      {icon}
      {label}
    </span>
  );
}
