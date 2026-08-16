import type {
  AgentUsage,
  CheckpointDetail,
  CheckpointSummary,
  HealthInfo,
  MapPoint,
  MemoryStats,
  RecentCase,
  SearchResult,
  StreamEvent,
  TimeseriesPoint,
} from "../types";

export interface StreamHandlers {
  onEvent: (evt: StreamEvent) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
}

/** Reads the /api/chat/stream SSE response and dispatches parsed JSON events. */
export async function streamChat(
  prompt: string,
  sessionId: string | null,
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, session_id: sessionId }),
      signal,
    });
  } catch (e) {
    handlers.onError?.(e instanceof Error ? e.message : "Network error");
    return;
  }

  if (!res.ok || !res.body) {
    handlers.onError?.(`Request failed (HTTP ${res.status})`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const jsonStr = line.slice(5).trim();
      if (!jsonStr) continue;
      try {
        const evt = JSON.parse(jsonStr) as StreamEvent;
        if (evt.type === "done") {
          handlers.onDone?.();
          continue;
        }
        handlers.onEvent(evt);
      } catch {
        // Ignore malformed/partial frames rather than crashing the stream.
      }
    }
  }
  handlers.onDone?.();
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export const fetchHealth = () => getJSON<HealthInfo>("/api/health");
export const fetchMemoryStats = () => getJSON<MemoryStats>("/api/memory/stats");
export const fetchRecentCases = (limit = 6) => getJSON<RecentCase[]>(`/api/memory/cases?limit=${limit}`);
export const fetchAgentUsage = () => getJSON<AgentUsage[]>("/api/memory/agent-usage");
export const fetchCasesTimeseries = (days = 14) => getJSON<TimeseriesPoint[]>(`/api/memory/timeseries?days=${days}`);

export const fetchEmbeddingMap = () => getJSON<{ points: MapPoint[]; error?: string }>("/api/memory/embedding-map");

export async function searchMemory(query: string, k = 5): Promise<SearchResult> {
  const res = await fetch("/api/memory/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, k }),
  });
  if (!res.ok) throw new Error(`search -> HTTP ${res.status}`);
  return res.json();
}

export const fetchCheckpoints = (sessionId: string) =>
  getJSON<CheckpointSummary[]>(`/api/sessions/${encodeURIComponent(sessionId)}/checkpoints`);

export const fetchCheckpointDetail = (sessionId: string, checkpointId: string) =>
  getJSON<CheckpointDetail>(
    `/api/sessions/${encodeURIComponent(sessionId)}/checkpoints/${encodeURIComponent(checkpointId)}`
  );
