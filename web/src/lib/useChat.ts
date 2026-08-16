import { useCallback, useRef, useState } from "react";
import { streamChat } from "./api";
import type { ChatMessage, StreamEvent, TraceEntry } from "../types";

const SESSION_KEY = "memorymesh.session_id";

function newId(): string {
  return crypto.randomUUID();
}

/**
 * Turns the raw multi-agent event stream into two things per turn:
 *  - a clean final answer (the synthesizer's text; falls back to the
 *    orchestrator's own text when it answers directly, e.g. a clarifying
 *    question with no specialists routed)
 *  - a trace timeline of every agent + tool call, kept separate so the
 *    chat bubble stays readable and the pipeline stays inspectable.
 */
export function useChat() {
  const [sessionId, setSessionId] = useState<string | null>(() => sessionStorage.getItem(SESSION_KEY));
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const newSession = useCallback(() => {
    abortRef.current?.abort();
    sessionStorage.removeItem(SESSION_KEY);
    setSessionId(null);
    setMessages([]);
    setIsStreaming(false);
  }, []);

  const send = useCallback(
    async (prompt: string) => {
      const userMsg: ChatMessage = { id: newId(), role: "user", content: prompt, streaming: false, trace: [] };
      const assistantId = newId();
      const assistantMsg: ChatMessage = { id: assistantId, role: "assistant", content: "", streaming: true, trace: [] };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      // Per-agent text buffers so we can pick the right source for the
      // final answer once the stream ends, without polluting the trace.
      const agentText: Record<string, string> = {};
      let sawDownstreamAgent = false;
      const toolIndexByUseId: Record<string, number> = {};

      const applyTrace = (updater: (trace: TraceEntry[]) => TraceEntry[]) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, trace: updater(m.trace) } : m))
        );
      };

      const setContent = (content: string) => {
        setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, content } : m)));
      };

      const handleEvent = (evt: StreamEvent) => {
        if (evt.type === "session" && evt.session_id) {
          sessionStorage.setItem(SESSION_KEY, evt.session_id);
          setSessionId(evt.session_id);
          return;
        }

        if (evt.type === "error" || (evt.error && !evt.type)) {
          const message = evt.content || evt.error || "Unknown error";
          setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, error: message } : m)));
          return;
        }

        if (evt.type === "agent_execution" && evt.agent) {
          if (evt.agent !== "orchestrator") sawDownstreamAgent = true;
          applyTrace((trace) => [
            ...trace,
            {
              key: `${evt.agent}-${evt.status}-${trace.length}`,
              kind: "agent",
              agent: evt.agent!,
              label: evt.agent!,
              status: evt.status ?? "started",
            },
          ]);
          return;
        }

        if (evt.type === "text" && evt.agent) {
          agentText[evt.agent] = (agentText[evt.agent] ?? "") + (evt.content ?? "");
          if (evt.agent === "synthesizer") {
            setContent(agentText.synthesizer);
          } else if (evt.agent === "orchestrator" && !sawDownstreamAgent) {
            // Provisional — only kept if no specialist/synthesizer ever runs
            // (the orchestrator answering directly, e.g. a clarifying question).
            setContent(agentText.orchestrator);
          }
          return;
        }

        if (evt.type === "tool" && evt.agent) {
          const useId = evt.tool_use_id ?? `${evt.agent}-${evt.name}`;
          applyTrace((trace) => {
            const idx = toolIndexByUseId[useId];
            const label = evt.status === "tool_result" ? undefined : evt.name;
            if (idx !== undefined && trace[idx]) {
              const next = [...trace];
              next[idx] = {
                ...next[idx],
                label: label ?? next[idx].label,
                status: evt.status ?? next[idx].status,
                detail: evt.text ?? next[idx].detail,
              };
              return next;
            }
            toolIndexByUseId[useId] = trace.length;
            return [
              ...trace,
              {
                key: useId,
                kind: "tool",
                agent: evt.agent!,
                label: evt.name ?? "tool",
                status: evt.status ?? "started",
                detail: evt.text,
              },
            ];
          });
        }
      };

      try {
        await streamChat(prompt, sessionId, {
          onEvent: handleEvent,
          onError: (message) => {
            setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, error: message } : m)));
          },
        }, controller.signal);
      } catch (e) {
        if (!(e instanceof DOMException && e.name === "AbortError")) {
          const message = e instanceof Error ? e.message : "Unknown error";
          setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, error: message } : m)));
        }
      } finally {
        // Clarifying-question fallback: if the synthesizer never produced
        // anything, use whatever the orchestrator said directly.
        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== assistantId) return m;
            const finalContent = agentText.synthesizer?.trim()
              ? agentText.synthesizer
              : m.content || agentText.orchestrator || "";
            return { ...m, content: finalContent, streaming: false };
          })
        );
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [sessionId]
  );

  return { sessionId, messages, isStreaming, send, newSession };
}
