import { useState, type FormEvent } from "react";
import { KeyRound, Loader2 } from "lucide-react";
import { login } from "../lib/api";

export default function Login({ onSuccess }: { onSuccess: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!password || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await login(password);
      if (result.ok) {
        onSuccess();
      } else {
        setError(result.error ?? "Incorrect password");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-ink-950 px-6">
      <form
        onSubmit={submit}
        className="flex w-full max-w-sm flex-col gap-4 rounded-2xl border border-ink-700 bg-ink-900/60 p-6"
      >
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-400">
            <KeyRound size={18} />
          </div>
          <h1 className="text-sm font-semibold text-slate-50">MemoryMesh Agent</h1>
          <p className="text-xs text-slate-500">Enter the access password to continue.</p>
        </div>

        <input
          type="password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Access password"
          className="rounded-lg border border-ink-600 bg-ink-850 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-emerald-500 focus:outline-none"
        />

        {error && <p className="text-xs text-rose-400">{error}</p>}

        <button
          type="submit"
          disabled={!password || submitting}
          className="flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-medium text-ink-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting && <Loader2 size={14} className="animate-spin" />}
          Enter
        </button>
      </form>
    </div>
  );
}
