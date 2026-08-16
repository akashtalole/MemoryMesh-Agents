import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertTriangle, Bot, User } from "lucide-react";
import AgentTrace from "./AgentTrace";
import type { ChatMessage } from "../types";

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
          isUser ? "bg-indigo-500/20 text-indigo-300" : "bg-emerald-500/20 text-emerald-300"
        }`}
      >
        {isUser ? <User size={14} /> : <Bot size={14} />}
      </div>

      <div className={`flex max-w-[75ch] flex-col ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-[13.5px] leading-relaxed ${
            isUser ? "bg-indigo-600/90 text-white" : "bg-ink-800 text-slate-100"
          }`}
        >
          {message.content ? (
            isUser ? (
              <p className="whitespace-pre-wrap">{message.content}</p>
            ) : (
              <div className="prose-chat">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
              </div>
            )
          ) : message.streaming ? (
            <TypingDots />
          ) : (
            <span className="text-slate-500">No response.</span>
          )}
        </div>

        {message.error && (
          <div className="mt-1.5 flex items-center gap-1.5 text-xs text-rose-400">
            <AlertTriangle size={12} />
            {message.error}
          </div>
        )}

        {!isUser && <AgentTrace trace={message.trace} />}
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1 py-0.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-500"
          style={{ animationDelay: `${i * 120}ms` }}
        />
      ))}
    </div>
  );
}
