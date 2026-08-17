import { useEffect, useState } from "react";
import NavRail, { type View } from "./components/NavRail";
import Header from "./components/Header";
import ChatPanel from "./components/ChatPanel";
import Login from "./components/Login";
import MemorySidebar from "./components/MemorySidebar";
import Dashboard from "./components/Dashboard";
import TimeTravel from "./components/TimeTravel";
import { useChat } from "./lib/useChat";
import { checkAuth, fetchHealth, logout } from "./lib/api";
import type { HealthInfo } from "./types";

const TITLES: Record<View, { title: string; subtitle: string }> = {
  chat: { title: "MemoryMesh Agent", subtitle: "Market surveillance, memory in CockroachDB" },
  dashboard: { title: "Dashboard", subtitle: "Live view into the agents' CockroachDB memory" },
};

type AuthState = "checking" | "authenticated" | "unauthenticated";

export default function App() {
  const [view, setView] = useState<View>("chat");
  const [historyOpen, setHistoryOpen] = useState(false);
  const { sessionId, messages, isStreaming, send, newSession } = useChat();
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [authState, setAuthState] = useState<AuthState>("checking");

  useEffect(() => {
    checkAuth()
      .then((r) => setAuthState(r.authenticated ? "authenticated" : "unauthenticated"))
      .catch(() => setAuthState("unauthenticated"));
  }, []);

  useEffect(() => {
    if (authState !== "authenticated") return;
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
  }, [authState]);

  if (authState === "checking") {
    return <div className="h-screen bg-ink-950" />;
  }

  if (authState === "unauthenticated") {
    return <Login onSuccess={() => setAuthState("authenticated")} />;
  }

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
          onSignOut={() => logout().then(() => setAuthState("unauthenticated"))}
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
