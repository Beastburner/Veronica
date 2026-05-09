"use client";

import { useEffect, useState } from "react";
import { BookOpen, RefreshCw, Sparkles } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type JournalEntry = {
  id: number;
  date: string;
  summary: string;
  created_at: string;
};

async function api<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...opts });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export default function JournalPanel() {
  const [entries, setEntries]   = useState<JournalEntry[]>([]);
  const [selected, setSelected] = useState<JournalEntry | null>(null);
  const [loading, setLoading]   = useState(false);
  const [generating, setGenerating] = useState(false);
  const [justWrote, setJustWrote]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await api<{ items: JournalEntry[] }>("/journal?limit=14");
      setEntries(data.items);
      if (data.items.length > 0 && !selected) {
        setSelected(data.items[0]);
      }
    } catch {
      setError("Failed to load journal entries.");
    } finally {
      setLoading(false);
    }
  }

  async function generateToday() {
    setGenerating(true);
    setError(null);
    try {
      const entry = await api<JournalEntry>("/journal/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: true }),
      });
      setEntries(prev => {
        const filtered = prev.filter(e => e.date !== entry.date);
        return [entry, ...filtered];
      });
      setSelected(entry);
      setJustWrote(true);
      setTimeout(() => setJustWrote(false), 2000);
    } catch {
      setError("Failed to generate today's journal.");
    } finally {
      setGenerating(false);
    }
  }

  useEffect(() => { load(); }, []);

  const today = new Date().toISOString().slice(0, 10);

  function formatDate(d: string) {
    try {
      return new Date(d + "T00:00:00").toLocaleDateString("en-IN", {
        weekday: "short", month: "short", day: "numeric",
      });
    } catch {
      return d;
    }
  }

  return (
    <div className="flex h-full gap-3">
      {/* Sidebar — entry list */}
      <div className="flex w-36 shrink-0 flex-col gap-1 overflow-y-auto">
        <button
          onClick={generateToday}
          disabled={generating}
          className="mb-1 flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-slate-300 transition hover:bg-white/10 disabled:opacity-50"
        >
          <Sparkles className="h-3 w-3 shrink-0" />
          {generating ? "Writing…" : justWrote ? "Done" : "Write Today"}
        </button>

        {loading && (
          <p className="text-center text-xs text-slate-500">Loading…</p>
        )}

        {entries.map(e => (
          <button
            key={e.id}
            onClick={() => setSelected(e)}
            className={`rounded-lg border px-2 py-1.5 text-left text-xs transition ${
              selected?.id === e.id
                ? "border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--accent-text)]"
                : "border-white/10 bg-white/5 text-slate-400 hover:bg-white/10"
            }`}
          >
            <span className={`block font-medium ${e.date === today ? "text-[var(--accent-strong)]" : ""}`}>
              {e.date === today ? "Today" : formatDate(e.date)}
            </span>
            <span className="mt-0.5 block truncate text-[10px] text-slate-500">
              {e.summary.slice(0, 40)}…
            </span>
          </button>
        ))}

        {!loading && entries.length === 0 && (
          <p className="text-center text-xs text-slate-600">No entries yet</p>
        )}
      </div>

      {/* Main — entry content */}
      <div className="flex flex-1 flex-col overflow-hidden rounded-lg border border-white/10 bg-white/5 p-4">
        {error && (
          <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>
        )}

        {selected ? (
          <>
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4" style={{ color: "var(--accent-strong)" }} />
                <span className="text-sm font-semibold text-white">
                  {selected.date === today ? "Today" : formatDate(selected.date)}
                </span>
                <span className="text-xs text-slate-500">{selected.date}</span>
              </div>
              <button
                onClick={load}
                className="rounded-lg border border-white/10 p-1 text-slate-400 transition hover:text-white"
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </button>
            </div>
            <p className="leading-relaxed text-sm text-slate-300 whitespace-pre-wrap">
              {selected.summary}
            </p>
          </>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <BookOpen className="h-8 w-8 text-slate-600" />
            <p className="text-sm text-slate-500">No entry selected</p>
            <button
              onClick={generateToday}
              disabled={generating}
              className="flex items-center gap-1.5 rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-3 py-1.5 text-xs text-[var(--accent-text)] transition hover:bg-[var(--accent)]/20 disabled:opacity-50"
            >
              <Sparkles className="h-3 w-3" />
              {generating ? "Writing…" : "Generate Today's Entry"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
