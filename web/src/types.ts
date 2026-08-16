export interface StreamEvent {
  type?: string;
  content?: string;
  agent?: string;
  status?: string;
  name?: string;
  tool_use_id?: string;
  text?: string;
  session_id?: string;
  error?: string;
}

export type TraceKind = "agent" | "tool";

export interface TraceEntry {
  key: string;
  kind: TraceKind;
  agent: string;
  label: string;
  status: string;
  detail?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming: boolean;
  trace: TraceEntry[];
  error?: string;
}

export interface MemoryStats {
  connected: boolean;
  cases: number;
  turns: number;
  sessions: number;
  error?: string;
}

export interface RecentCase {
  case_id: string | null;
  query: string | null;
  recorded_at: string | null;
  agents: string | null;
}

export interface HealthInfo {
  status: string;
  backend_mode: "local" | "agentcore" | string;
  runtime_arn: string | null;
  region: string;
  cockroachdb_connected: boolean;
  cockroachdb_error?: string;
}

export interface AgentUsage {
  agent: string;
  count: number;
}

export interface TimeseriesPoint {
  date: string;
  count: number;
}

/**
 * Fixed-order categorical palette (dark-surface steps), validated against
 * this app's #0a0c10 background with the dataviz skill's validator — all
 * checks pass (lightness band, chroma floor, CVD ΔE, normal-vision floor,
 * contrast). Never reassign a slot by rank; a 9th series folds into "Other"
 * rather than generating a new hue. One adjacent pair sits in the 6-8 CVD
 * warn band, so bars also carry a direct value label (never color alone).
 */
export const CATEGORICAL_PALETTE = [
  "#3987e5", // blue
  "#d95926", // orange
  "#199e70", // aqua
  "#c98500", // yellow
  "#d55181", // magenta
  "#008300", // green
  "#9085e9", // violet
  "#e66767", // red
];

/** Fixed status palette — reserved for state, never reused as a series color. */
export const STATUS_COLORS = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
} as const;

export const AGENT_LABELS: Record<string, string> = {
  recall_case_memory: "Memory recall",
  orchestrator: "Orchestrator",
  security_monitor: "Security Monitor",
  broker_monitor: "Broker Monitor",
  risk_monitor: "Risk Monitor",
  intel_analyst: "Intel Analyst",
  memory_ops: "Memory Ops",
  compliance_officer: "Compliance Officer",
  case_triage: "Case Triage",
  audit_reviewer: "Audit Reviewer",
  synthesizer: "Synthesizer",
  persist_case_memory: "Memory write-back",
};

export const AGENT_INITIALS: Record<string, string> = {
  orchestrator: "OR",
  security_monitor: "SM",
  broker_monitor: "BM",
  risk_monitor: "RM",
  intel_analyst: "IA",
  memory_ops: "MO",
  compliance_officer: "CO",
  case_triage: "CT",
  audit_reviewer: "AR",
  synthesizer: "SY",
};

/**
 * Fixed identity -> palette-slot order. Color must follow the entity, never
 * its rank in a sorted list (a bar chart re-sorted by count must not
 * repaint any agent a different color) — this is the single source of
 * truth `agentColor` and every chart that colors by agent draws from.
 */
const AGENT_COLOR_ORDER = [
  "security_monitor",
  "broker_monitor",
  "risk_monitor",
  "intel_analyst",
  "memory_ops",
  "compliance_officer",
  "case_triage",
  "audit_reviewer",
];

export function agentColor(agent: string): string {
  const idx = AGENT_COLOR_ORDER.indexOf(agent);
  return CATEGORICAL_PALETTE[idx >= 0 ? idx : CATEGORICAL_PALETTE.length - 1];
}

export interface MapPoint {
  case_id: string | null;
  query: string | null;
  recorded_at: string | null;
  x: number;
  y: number;
}

export interface SearchMatch {
  score: number;
  case_id: string | null;
  query: string | null;
  recorded_at: string | null;
  findings: string | null;
}

export interface SearchResult {
  query: string;
  point: { x: number; y: number } | null;
  matches: SearchMatch[];
}

export interface CheckpointSummary {
  checkpoint_id: string;
  step: number;
  source: string;
  ts: string;
  node_labels: string[];
}

export interface CheckpointDetail extends CheckpointSummary {
  state: Record<string, unknown>;
}
