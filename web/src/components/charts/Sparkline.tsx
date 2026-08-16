interface Props {
  data: number[];
  color?: string;
}

/** Minimal trend line for a stat tile — no axes, no hover, just shape. */
export default function Sparkline({ data, color = "#3987e5" }: Props) {
  if (data.length < 2) return <div className="h-7" />;

  const max = Math.max(1, ...data);
  const w = 100;
  const h = 28;
  const points = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - (v / max) * h}`).join(" ");

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-7 w-full" preserveAspectRatio="none">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity={0.85}
      />
    </svg>
  );
}
