import type { ReactNode } from "react";
import Sparkline from "./charts/Sparkline";

interface Props {
  label: string;
  value: string | number;
  icon: ReactNode;
  trend?: number[];
  toneColor?: string;
}

/** Stat-tile contract: sentence-case label (no colon), semibold value,
 * optional 12-point sparkline trend. */
export default function StatTile({ label, value, icon, trend, toneColor }: Props) {
  return (
    <div className="rounded-xl border border-ink-700 bg-ink-900/60 p-4">
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wide text-slate-500">{label}</span>
        <span className="text-slate-600">{icon}</span>
      </div>
      <p className="mt-1.5 text-2xl font-semibold text-slate-50">{value}</p>
      {trend && (
        <div className="mt-2">
          <Sparkline data={trend} color={toneColor} />
        </div>
      )}
    </div>
  );
}
