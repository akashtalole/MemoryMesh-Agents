import { useEffect, useState } from "react";
import NavRail, { type View } from "./components/NavRail";
import Header from "./components/Header";
import ChatPanel from "./components/ChatPanel";
import MemorySidebar from "./components/MemorySidebar";
import Dashboard from "./components/Dashboard";
import TimeTravel from "./components/TimeTravel";
import { useChat } from "./lib/useChat";
import { fetchHealth } from "./lib/api";
import type { HealthInfo } from "./types";

const TITLES: Record<View, { title: string; subtitle: string }> = {
  chat: { title: "MemoryMesh Agent", subtitle: "Market surveillance, memory in CockroachDB" },
  dashboard: { title: "Dashboard", subtitle: "Live view into the agents' CockroachDB memory" },
};

export default function App() {
  const [view, setView] = useState<View>("chat");
  const [historyOpen, setHistoryOpen] = useState(false);
  const { sessionId, messages, isStreaming, send, newSession } = useChat();
  const [health, setHealth] = useState<HealthInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const h = await fetchHealth();
        if (!cancelled) setHealth(h);
      } catch {
        /* keep last known health */
      }
    };
    poll();
    const id = setInterval(poll, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="flex h-screen bg-ink-950">
      <NavRail view={view} onChange={setView} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          {...TITLES[view]}
          health={health}
          sessionId={view === "chat" ? sessionId : undefined}
          onNewSession={view === "chat" ? newSession : undefined}
          onOpenHistory={view === "chat" ? () => setHistoryOpen(true) : undefined}
        />
        <div className="flex min-h-0 flex-1">
          {view === "chat" ? (
            <>
              <ChatPanel messages={messages} isStreaming={isStreaming} onSend={send} />
              <MemorySidebar />
            </>
          ) : (
            <Dashboard health={health} />
          )}
        </div>
      </div>
      <TimeTravel sessionId={sessionId} open={historyOpen} onClose={() => setHistoryOpen(false)} />
    </div>
  );
}
