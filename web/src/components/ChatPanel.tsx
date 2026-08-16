import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import Composer from "./Composer";
import type { ChatMessage } from "../types";

interface Props {
  messages: ChatMessage[];
  isStreaming: boolean;
  onSend: (prompt: string) => void;
}

export default function ChatPanel({ messages, isStreaming, onSend }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-6 sm:px-8">
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-6">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
      <div className="mx-auto w-full max-w-3xl">
        <Composer disabled={isStreaming} onSend={onSend} />
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="mx-auto flex h-full max-w-md flex-col items-center justify-center text-center text-slate-500">
      <div className="mb-3 text-3xl">🪳</div>
      <h2 className="text-sm font-semibold text-slate-300">Ask the surveillance agents</h2>
      <p className="mt-1 text-xs leading-relaxed">
        Every investigation is checkpointed, logged, and embedded into
        CockroachDB — ask a question, then ask something similar later and
        watch the orchestrator recall it.
      </p>
    </div>
  );
}
