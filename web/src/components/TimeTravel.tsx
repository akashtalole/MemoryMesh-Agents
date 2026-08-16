import { useEffect, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { fetchCheckpointDetail, fetchCheckpoints } from "../lib/api";
import { AGENT_LABELS, agentColor, type CheckpointDetail, type CheckpointSummary } from "../types";

interface Props {
  sessionId: string | null;
  open: boolean;
  onClose: () => void;
}

/**
 * Scrubs through a session's LangGraph checkpoint history — every node
 * transition CockroachDB already has snapshotted via AsyncCockroachDBSaver.
 * This doesn't create anything new; it makes an existing capability
 * (resumability / time travel) visible instead of invisible.
 */
export default function TimeTravel({ sessionId, open, onClose }: Props) {
  const [checkpoints, setCheckpoints] = useState<CheckpointSummary[]>([]);
  const [selected, setSelected] = useState<number>(0);
  const [detail, setDetail] = useState<CheckpointDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !sessionId) return;
    setLoading(true);
    fetchCheckpoints(sessionId)
      .then((items) => {
        setCheckpoints(items);
        setSelected(items.length - 1);
      })
      .catch(() => setCheckpoints([]))
      .finally(() => setLoading(false));
  }, [open, sessionId]);

  useEffect(() => {
    if (!open || !sessionId || checkpoints.length === 0) return;
    const cp = checkpoints[selected];
    if (!cp) return;
    fetchCheckpointDetail(sessionId, cp.checkpoint_id)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [open, sessionId, selected, checkpoints]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose}>
      <div
        className="flex h-full w-full max-w-lg flex-col border-l border-ink-700 bg-ink-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ink-700 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-100">Time travel</h2>
            <p className="text-[11px] text-slate-500">
              Session {sessionId?.slice(0, 8)} — {checkpoints.length} checkpoint{checkpoints.length === 1 ? "" : "s"} in
              CockroachDB
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-500 hover:bg-ink-800 hover:text-slate-200">
            <X size={16} />
          </button>
        </div>

        {loading ? (
          <p className="p-4 text-xs text-slate-500">Loading checkpoint history…</p>
        ) : checkpoints.length === 0 ? (
          <p className="p-4 text-xs text-slate-500">
            No checkpoints found for this session yet — ask a question first.
          </p>
        ) : (
          <>
            {/* Scrubber */}
            <div className="border-b border-ink-700 px-4 py-3">
              <input
                type="range"
                min={0}
                max={checkpoints.length - 1}
                value={selected}
                onChange={(e) => setSelected(Number(e.target.value))}
                className="w-full accent-emerald-500"
              />
              <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
                <span>step {checkpoints[0]?.step}</span>
                <span>
                  step {checkpoints[selected]?.step} of {checkpoints.length}
                </span>
                <span>step {checkpoints[checkpoints.length - 1]?.step}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {checkpoints[selected]?.node_labels.map((label) => (
                  <span
                    key={label}
                    className="rounded-full px-2 py-0.5 text-[10px] font-medium text-ink-950"
                    style={{ backgroundColor: agentColor(labelToAgent(label)) }}
                  >
                    {label}
                  </span>
                ))}
              </div>
            </div>

            {/* State snapshot */}
            <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-3">
              {detail ? (
                <StateSnapshot detail={detail} />
              ) : (
                <p className="text-xs text-slate-600">Loading state…</p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function labelToAgent(label: string): string {
  const entry = Object.entries(AGENT_LABELS).find(([, v]) => v === label);
  return entry ? entry[0] : label;
}

function StateSnapshot({ detail }: { detail: CheckpointDetail }) {
  const entries = Object.entries(detail.state);
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[10px] text-slate-600">{new Date(detail.ts).toLocaleString()}</p>
      {entries.map(([key, value]) => (
        <StateField key={key} fieldKey={key} value={value} />
      ))}
    </div>
  );
}

function StateField({ fieldKey, value }: { fieldKey: string; value: unknown }) {
  if (value === null || value === undefined) return null;

  const title = fieldKey.replace(/_/g, " ");

  // Strands agent message-history channels are trimmed server-side to a count.
  if (isRecord(value) && "message_count" in value) {
    return (
      <Field title={title}>
        <span className="text-slate-500">{String(value.message_count)} message(s) exchanged</span>
      </Field>
    );
  }

  if (fieldKey === "similar_cases" && isRecord(value) && Array.isArray(value.cases)) {
    const cases = value.cases as { case_id?: string; query?: string; score?: number }[];
    if (cases.length === 0) return null;
    return (
      <Field title="Recalled similar cases">
        <ul className="flex flex-col gap-1">
          {cases.map((c) => (
            <li key={c.case_id} className="text-slate-400">
              <span className="text-slate-300">{c.query}</span>{" "}
              <span className="tabular-nums text-slate-600">({(c.score ?? 0).toFixed(2)})</span>
            </li>
          ))}
        </ul>
      </Field>
    );
  }

  if (isRecord(value) && Array.isArray(value.business_insights)) {
    return (
      <Field title={title}>
        <ul className="list-disc space-y-0.5 pl-4 text-slate-400">
          {value.business_insights.map((line: unknown, i: number) => (
            <li key={i}>{String(line)}</li>
          ))}
        </ul>
      </Field>
    );
  }

  if (fieldKey === "synthesizer_insights" && typeof value === "string") {
    return (
      <Field title="Synthesized answer">
        <p className="whitespace-pre-wrap text-slate-300">{value}</p>
      </Field>
    );
  }

  if (Array.isArray(value)) {
    return (
      <Field title={title}>
        <span className="text-slate-400">{value.length ? value.join(", ") : "—"}</span>
      </Field>
    );
  }

  if (typeof value === "object") {
    return (
      <Field title={title}>
        <pre className="overflow-x-auto rounded-md bg-ink-950 p-2 text-[10px] text-slate-500">
          {JSON.stringify(value, null, 2)}
        </pre>
      </Field>
    );
  }

  return (
    <Field title={title}>
      <span className="text-slate-400">{String(value)}</span>
    </Field>
  );
}

function Field({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-600">{title}</p>
      <div className="text-[11px] leading-relaxed">{children}</div>
    </div>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
