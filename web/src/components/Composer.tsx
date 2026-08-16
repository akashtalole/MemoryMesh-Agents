import { useState, type KeyboardEvent } from "react";
import { Send } from "lucide-react";

interface Props {
  disabled: boolean;
  onSend: (prompt: string) => void;
}

const SAMPLE_PROMPTS = [
  "What was the trading activity for AAPL on March 15, 2024 and which brokers were most active?",
  "How many past investigations do we have stored, and have we looked at broker risk on MSFT before?",
  "Is ALPHA_CAPITAL's AAPL trading on March 15, 2024 a compliance issue, and how urgent is it?",
];

export default function Composer({ disabled, onSend }: Props) {
  const [value, setValue] = useState("");

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-ink-700 bg-ink-900/80 p-4">
      {value.length === 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {SAMPLE_PROMPTS.map((p) => (
            <button
              key={p}
              onClick={() => setValue(p)}
              className="rounded-full border border-ink-700 bg-ink-850 px-3 py-1 text-[11px] text-slate-400 transition hover:border-emerald-500/40 hover:text-emerald-300"
            >
              {p.length > 56 ? p.slice(0, 56) + "…" : p}
            </button>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2 rounded-2xl border border-ink-700 bg-ink-850 px-3 py-2 focus-within:border-emerald-500/50">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="Ask about market surveillance, or about the system's own memory…"
          className="max-h-40 flex-1 resize-none bg-transparent py-1.5 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none"
        />
        <button
          onClick={submit}
          disabled={disabled || !value.trim()}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-ink-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-ink-700 disabled:text-slate-600"
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}
