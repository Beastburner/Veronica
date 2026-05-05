"use client";

import {
  Bell,
  BrainCircuit,
  Calendar,
  CheckSquare,
  Link,
  NotebookPen,
  RefreshCw,
  Send,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type LogEntry = {
  id: number;
  entry_type: string;
  title: string;
  content: string | null;
  metadata: string | null;
  created_at: string;
};

const ENTRY_ICONS: Record<string, React.ReactNode> = {
  task_created: <CheckSquare size={12} className="text-cyan-400" />,
  task_completed: <CheckSquare size={12} className="text-emerald-400" />,
  reminder_fired: <Bell size={12} className="text-yellow-400" />,
  reminder_set: <Bell size={12} className="text-slate-400" />,
  note_created: <NotebookPen size={12} className="text-purple-400" />,
  meeting_scheduled: <Calendar size={12} className="text-blue-400" />,
  email_sent: <Send size={12} className="text-cyan-400" />,
  oauth_connected: <Link size={12} className="text-emerald-400" />,
  oauth_disconnected: <Link size={12} className="text-pink-400" />,
  ai_interaction: <BrainCircuit size={12} className="text-[var(--accent-text)]" />,
};

const ENTRY_LABELS: Record<string, string> = {
  task_created: "Task created",
  task_completed: "Task done",
  reminder_fired: "Reminder fired",
  reminder_set: "Reminder set",
  note_created: "Note saved",
  meeting_scheduled: "Meeting scheduled",
  email_sent: "Email sent",
  oauth_connected: "Service connected",
  oauth_disconnected: "Service disconnected",
  ai_interaction: "AI interaction",
};

function timeAgo(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return "just now";
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  } catch {
    return "";
  }
}

const FILTER_OPTIONS = [
  { value: "", label: "All" },
  { value: "task_completed", label: "Tasks" },
  { value: "meeting_scheduled", label: "Meetings" },
  { value: "email_sent", label: "Emails" },
  { value: "reminder_fired", label: "Reminders" },
  { value: "note_created", label: "Notes" },
];

export function ActivityPanel() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 15;

  const fetchEntries = useCallback(async (entryType: string, pageNum: number) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        skip: String(pageNum * PAGE_SIZE),
        limit: String(PAGE_SIZE),
      });
      if (entryType) params.set("entry_type", entryType);
      const res = await fetch(`${API}/life-log?${params}`);
      const data = await res.json();
      setEntries(data.items as LogEntry[]);
      setTotal(data.pagination.total as number);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setPage(0);
    void fetchEntries(filter, 0);
  }, [filter, fetchEntries]);

  return (
    <div className="hud-panel rounded-lg p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <Zap size={16} /> Activity Log
        </p>
        <div className="flex gap-2 items-center">
          <span className="text-[10px] text-slate-500">{total} entries</span>
          <button
            onClick={() => void fetchEntries(filter, page)}
            disabled={loading}
            className="rounded border border-white/10 p-1 text-slate-400 hover:text-white transition disabled:opacity-40"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      <div className="mb-3 flex gap-1.5 flex-wrap">
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setFilter(opt.value)}
            className={`rounded px-2.5 py-1 text-[10px] font-semibold transition ${
              filter === opt.value
                ? "bg-[var(--accent)]/20 text-[var(--accent-text)] border border-[var(--accent)]/40"
                : "bg-white/[0.04] text-slate-400 border border-white/10 hover:text-slate-200"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div className="space-y-1.5 max-h-72 overflow-y-auto">
        {entries.length === 0 && !loading && (
          <p className="text-xs text-slate-500 py-4 text-center">
            No activity logged yet. Complete tasks, send emails, or schedule meetings to see your log here.
          </p>
        )}
        {entries.map((entry) => (
          <div
            key={entry.id}
            className="flex items-start gap-2.5 rounded-lg border border-white/[0.06] bg-black/20 px-3 py-2"
          >
            <div className="mt-0.5 shrink-0">
              {ENTRY_ICONS[entry.entry_type] ?? <Zap size={12} className="text-slate-400" />}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-xs text-slate-200 truncate">{entry.title}</p>
                <p className="text-[10px] text-slate-500 shrink-0">{timeAgo(entry.created_at)}</p>
              </div>
              <p className="text-[10px] text-slate-500">
                {ENTRY_LABELS[entry.entry_type] ?? entry.entry_type.replace(/_/g, " ")}
              </p>
            </div>
          </div>
        ))}
      </div>

      {total > PAGE_SIZE && (
        <div className="mt-3 flex items-center justify-between">
          <button
            disabled={page === 0}
            onClick={() => { const p = page - 1; setPage(p); void fetchEntries(filter, p); }}
            className="rounded border border-white/10 px-3 py-1 text-xs text-slate-400 disabled:opacity-30 hover:text-white transition"
          >
            Previous
          </button>
          <span className="text-[10px] text-slate-500">
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}
          </span>
          <button
            disabled={(page + 1) * PAGE_SIZE >= total}
            onClick={() => { const p = page + 1; setPage(p); void fetchEntries(filter, p); }}
            className="rounded border border-white/10 px-3 py-1 text-xs text-slate-400 disabled:opacity-30 hover:text-white transition"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
