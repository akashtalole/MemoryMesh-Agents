import { LayoutDashboard, MessageSquare } from "lucide-react";

export type View = "chat" | "dashboard";

interface Props {
  view: View;
  onChange: (view: View) => void;
}

const ITEMS: { id: View; label: string; icon: typeof MessageSquare }[] = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
];

export default function NavRail({ view, onChange }: Props) {
  return (
    <nav className="flex w-16 shrink-0 flex-col items-center gap-1 border-r border-ink-700 bg-ink-900/80 py-4">
      <div className="mb-4 flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/15 text-lg">
        🪳
      </div>

      {ITEMS.map(({ id, label, icon: Icon }) => {
        const active = view === id;
        return (
          <button
            key={id}
            onClick={() => onChange(id)}
            title={label}
            aria-current={active}
            className={`group relative flex h-12 w-12 flex-col items-center justify-center gap-1 rounded-xl transition ${
              active
                ? "bg-emerald-500/15 text-emerald-300"
                : "text-slate-500 hover:bg-ink-800 hover:text-slate-300"
            }`}
          >
            {active && (
              <span className="absolute left-0 h-5 w-0.5 -translate-x-[calc(0.5rem+2px)] rounded-full bg-emerald-400" />
            )}
            <Icon size={18} />
            <span className="text-[9px] font-medium leading-none">{label}</span>
          </button>
        );
      })}
    </nav>
  );
}
