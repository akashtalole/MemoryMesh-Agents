import { useMemo, useRef, useState, type MouseEvent } from "react";
import { CATEGORICAL_PALETTE, type TimeseriesPoint } from "../../types";
import EmptyChart from "./EmptyChart";

interface Props {
  data: TimeseriesPoint[];
}

const VB_W = 600;
const VB_H = 190;
const PAD = { top: 14, right: 10, bottom: 24, left: 30 };
const PLOT_X0 = PAD.left;
const PLOT_X1 = VB_W - PAD.right;
const PLOT_Y0 = PAD.top;
const PLOT_Y1 = VB_H - PAD.bottom;
const SERIES_COLOR = CATEGORICAL_PALETTE[0];

/**
 * Single-series line + area chart (cases recorded per day). One hue, no
 * legend needed — the card title already names the series. 2px line,
 * round joins, a 10%-opacity area wash, hairline gridlines, and a
 * crosshair + tooltip on hover, per the mark spec.
 */
export default function TimeSeriesChart({ data }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const hasData = data.length > 0;
  const max = Math.max(1, ...data.map((d) => d.count));
  const yTicks = useMemo(() => {
    const mid = Math.ceil(max / 2);
    return Array.from(new Set([0, mid, max]));
  }, [max]);

  const xFor = (i: number) => {
    if (data.length <= 1) return PLOT_X0;
    return PLOT_X0 + (i / (data.length - 1)) * (PLOT_X1 - PLOT_X0);
  };
  const yFor = (value: number) => PLOT_Y1 - (value / max) * (PLOT_Y1 - PLOT_Y0);

  const linePath = data.map((d, i) => `${i === 0 ? "M" : "L"}${xFor(i)},${yFor(d.count)}`).join(" ");
  const areaPath = hasData
    ? `${linePath} L${xFor(data.length - 1)},${PLOT_Y1} L${xFor(0)},${PLOT_Y1} Z`
    : "";

  const labelEvery = Math.max(1, Math.ceil(data.length / 6));

  const handleMove = (e: MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg || data.length === 0) return;
    const rect = svg.getBoundingClientRect();
    const relX = ((e.clientX - rect.left) / rect.width) * VB_W;
    const ratio = (relX - PLOT_X0) / (PLOT_X1 - PLOT_X0);
    const idx = Math.round(ratio * (data.length - 1));
    setHoverIdx(Math.min(Math.max(idx, 0), data.length - 1));
  };

  if (!hasData) {
    return <EmptyChart label="No cases recorded in this window yet." />;
  }

  const hovered = hoverIdx !== null ? data[hoverIdx] : null;

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        className="h-[150px] w-full"
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverIdx(null)}
      >
        {/* gridlines */}
        {yTicks.map((t) => (
          <g key={t}>
            <line
              x1={PLOT_X0}
              x2={PLOT_X1}
              y1={yFor(t)}
              y2={yFor(t)}
              stroke="#232838"
              strokeWidth={1}
            />
            <text x={PLOT_X0 - 6} y={yFor(t) + 3} textAnchor="end" className="fill-slate-600 text-[9px]">
              {t}
            </text>
          </g>
        ))}

        {/* x-axis labels */}
        {data.map((d, i) =>
          i % labelEvery === 0 || i === data.length - 1 ? (
            <text
              key={d.date}
              x={xFor(i)}
              y={VB_H - 6}
              textAnchor="middle"
              className="fill-slate-600 text-[9px]"
            >
              {formatShortDate(d.date)}
            </text>
          ) : null
        )}

        {/* area + line */}
        <path d={areaPath} fill={SERIES_COLOR} fillOpacity={0.1} stroke="none" />
        <path d={linePath} fill="none" stroke={SERIES_COLOR} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

        {/* end marker */}
        <circle
          cx={xFor(data.length - 1)}
          cy={yFor(data[data.length - 1].count)}
          r={4}
          fill={SERIES_COLOR}
          stroke="#0f1218"
          strokeWidth={2}
        />

        {/* crosshair */}
        {hoverIdx !== null && (
          <>
            <line
              x1={xFor(hoverIdx)}
              x2={xFor(hoverIdx)}
              y1={PLOT_Y0}
              y2={PLOT_Y1}
              stroke="#333a4f"
              strokeWidth={1}
              strokeDasharray="2,2"
            />
            <circle
              cx={xFor(hoverIdx)}
              cy={yFor(data[hoverIdx].count)}
              r={4}
              fill={SERIES_COLOR}
              stroke="#0f1218"
              strokeWidth={2}
            />
          </>
        )}
      </svg>

      {hovered && hoverIdx !== null && (
        <div
          className="pointer-events-none absolute top-1 -translate-x-1/2 whitespace-nowrap rounded-md border border-ink-600 bg-ink-850 px-2 py-1 text-[11px] text-slate-200 shadow-lg"
          style={{ left: `${(xFor(hoverIdx) / VB_W) * 100}%` }}
        >
          <span className="font-medium">{formatShortDate(hovered.date)}</span>
          <span className="text-slate-500"> — {hovered.count} case{hovered.count === 1 ? "" : "s"}</span>
        </div>
      )}
    </div>
  );
}

function formatShortDate(iso: string): string {
  try {
    return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}
