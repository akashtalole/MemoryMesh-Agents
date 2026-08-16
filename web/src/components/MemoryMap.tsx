import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { fetchEmbeddingMap, searchMemory } from "../lib/api";
import type { MapPoint, SearchMatch } from "../types";
import EmptyChart from "./charts/EmptyChart";

const VB_W = 480;
const VB_H = 300;
const PAD = 16;
const POLL_MS = 20000;
const CASE_COLOR = "#3987e5";
const MATCH_COLOR = "#0ca30c";
const QUERY_COLOR = "#fab219";

function toSvg(x: number, y: number) {
  // x, y come in roughly [-1, 1] from the server's PCA projection.
  const sx = PAD + ((x + 1) / 2) * (VB_W - 2 * PAD);
  const sy = PAD + ((1 - y) / 2) * (VB_H - 2 * PAD); // flip y for screen coords
  return [sx, sy];
}

/**
 * A live 2D projection of every case_memory embedding (server-side PCA over
 * the real 384-dim vectors) plus a search box that projects a typed query
 * onto the same basis — the distributed vector index rendered as something
 * you can look at and query, not just a number on a stat tile.
 */
export default function MemoryMap() {
  const [points, setPoints] = useState<MapPoint[]>([]);
  const [hover, setHover] = useState<MapPoint | null>(null);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [queryPoint, setQueryPoint] = useState<{ x: number; y: number } | null>(null);
  const [matches, setMatches] = useState<SearchMatch[]>([]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const { points: p } = await fetchEmbeddingMap();
        if (!cancelled) setPoints(p);
      } catch {
        /* keep last known points */
      }
    };
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const matchedIds = useMemo(() => new Set(matches.map((m) => m.case_id).filter(Boolean)), [matches]);

  const runSearch = async () => {
    const q = query.trim();
    if (!q || searching) return;
    setSearching(true);
    try {
      const result = await searchMemory(q, 5);
      setQueryPoint(result.point);
      setMatches(result.matches);
    } catch {
      setMatches([]);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <div className="relative flex-1">
          <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-600" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch()}
            placeholder="Search case memory — e.g. 'wash trading on AAPL'…"
            className="w-full rounded-lg border border-ink-700 bg-ink-850 py-1.5 pl-8 pr-3 text-xs text-slate-100 placeholder:text-slate-600 focus:border-emerald-500/50 focus:outline-none"
          />
        </div>
        <button
          onClick={runSearch}
          disabled={searching || !query.trim()}
          className="rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-medium text-ink-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-ink-700 disabled:text-slate-600"
        >
          {searching ? "Searching…" : "Search"}
        </button>
      </div>

      {points.length === 0 ? (
        <EmptyChart label="No cases in memory yet — ask a question to plot the first point." />
      ) : (
        <div className="relative">
          <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="h-[260px] w-full">
            <rect x={0} y={0} width={VB_W} height={VB_H} rx={8} className="fill-ink-850" />

            {points.map((p) => {
              const [sx, sy] = toSvg(p.x, p.y);
              const isMatch = p.case_id && matchedIds.has(p.case_id);
              return (
                <circle
                  key={p.case_id ?? `${p.x}-${p.y}`}
                  cx={sx}
                  cy={sy}
                  r={isMatch ? 5 : 3.5}
                  fill={isMatch ? MATCH_COLOR : CASE_COLOR}
                  fillOpacity={isMatch ? 0.95 : 0.6}
                  stroke={isMatch ? "#0f1218" : "none"}
                  strokeWidth={isMatch ? 2 : 0}
                  onMouseEnter={() => setHover(p)}
                  onMouseLeave={() => setHover((h) => (h === p ? null : h))}
                  className="cursor-pointer transition-all"
                />
              );
            })}

            {queryPoint &&
              (() => {
                const [sx, sy] = toSvg(queryPoint.x, queryPoint.y);
                return (
                  <g>
                    <circle cx={sx} cy={sy} r={9} fill={QUERY_COLOR} fillOpacity={0.25}>
                      <animate attributeName="r" values="7;13;7" dur="1.8s" repeatCount="indefinite" />
                      <animate attributeName="fill-opacity" values="0.35;0.05;0.35" dur="1.8s" repeatCount="indefinite" />
                    </circle>
                    <circle cx={sx} cy={sy} r={5} fill={QUERY_COLOR} stroke="#0f1218" strokeWidth={2} />
                  </g>
                );
              })()}
          </svg>

          {hover && (
            <div className="pointer-events-none absolute left-2 top-2 max-w-[70%] rounded-md border border-ink-600 bg-ink-850 px-2 py-1.5 text-[11px] text-slate-200 shadow-lg">
              <p className="line-clamp-2 text-slate-200">{hover.query}</p>
              <p className="mt-0.5 text-[10px] text-slate-500">{hover.recorded_at}</p>
            </div>
          )}

          <div className="mt-2 flex items-center gap-4 text-[10px] text-slate-500">
            <Legend color={CASE_COLOR} label="Case in memory" />
            <Legend color={MATCH_COLOR} label="Search match" />
            <Legend color={QUERY_COLOR} label="Your query" />
          </div>
        </div>
      )}

      {matches.length > 0 && (
        <div className="mt-3 flex flex-col gap-1.5">
          {matches.map((m) => (
            <div
              key={m.case_id ?? m.query}
              className="flex items-center justify-between gap-3 rounded-md bg-ink-800/60 px-2.5 py-1.5 text-[11px]"
            >
              <span className="truncate text-slate-300">{m.query}</span>
              <span className="shrink-0 tabular-nums text-slate-500">{(m.score ?? 0).toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
