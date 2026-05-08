"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarClock, CheckSquare, Flame, Globe, NotebookPen, TimerReset } from "lucide-react";
import { ActivityPanel } from "@/components/ActivityPanel";
import { CalendarPanel } from "@/components/CalendarPanel";
import { EmailPanel } from "@/components/EmailPanel";
import { GitHubPanel } from "@/components/GitHubPanel";
import { SpotifyPanel } from "@/components/SpotifyPanel";
import { WhatsAppPanel } from "@/components/WhatsAppPanel";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Task     = { id: number; description: string; priority: string; status: string };
type Note     = { id: number; content: string; created_at: string };
type Reminder = { id: number; content: string; due_at: string | null; due_label?: string | null; status: string };
type Briefing = { summary: string; focus_recommendation: string; top_tasks: Task[]; reminders: Reminder[] };
type Habit    = { id: number; name: string; description: string; frequency: string; color: string; done_today: boolean; streak: number };
type Article  = { title: string; link: string; summary: string; published: string; feed_title?: string; feed_category?: string };
type NewsDigest = { feeds: Article[]; total: number; fetched_at: string };

async function api<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...opts });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

type Tab = "operations" | "habits" | "news" | "email" | "calendar" | "activity" | "github" | "spotify" | "whatsapp";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "operations", label: "Ops" },
  { id: "habits",     label: "Habits" },
  { id: "news",       label: "News" },
  { id: "email",      label: "Mail" },
  { id: "calendar",   label: "Calendar" },
  { id: "activity",   label: "Activity" },
  { id: "github",     label: "GitHub" },
  { id: "spotify",    label: "Spotify" },
  { id: "whatsapp",   label: "WhatsApp" },
];

export function OperationsPanels() {
  const [activeTab, setActiveTab] = useState<Tab>("operations");
  const [briefing, setBriefing]   = useState<Briefing | null>(null);
  const [tasks, setTasks]         = useState<Task[]>([]);
  const [notes, setNotes]         = useState<Note[]>([]);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [habits, setHabits]       = useState<Habit[]>([]);
  const [news, setNews]           = useState<NewsDigest | null>(null);
  const [newsLoading, setNewsLoading] = useState(false);

  const [taskInput, setTaskInput]       = useState("");
  const [noteInput, setNoteInput]       = useState("");
  const [reminderInput, setReminderInput] = useState("");
  const [habitInput, setHabitInput]     = useState("");

  const [busy, setBusy]   = useState<null | "task" | "note" | "reminder" | "habit">(null);
  const [error, setError] = useState<string | null>(null);
  const [notificationReady, setNotificationReady] = useState(false);

  const pendingTasks = useMemo(() => tasks.filter((t) => t.status === "pending"), [tasks]);

  async function refreshOps() {
    try {
      const [bd, td, nd, rd] = await Promise.all([
        api<Briefing>("/briefing/today"),
        api<{ items: Task[] }>("/tasks?limit=6"),
        api<{ items: Note[] }>("/notes?limit=4"),
        api<{ items: Reminder[] }>("/reminders?limit=4"),
      ]);
      setBriefing(bd); setTasks(td.items); setNotes(nd.items); setReminders(rd.items);
      setError(null);
    } catch { setError("Failed to load. Is the API running on port 8000?"); }
  }

  async function refreshHabits() {
    try {
      const data = await api<{ items: Habit[] }>("/habits");
      setHabits(data.items);
    } catch { /* silent */ }
  }

  async function loadNews() {
    setNewsLoading(true);
    try {
      const data = await api<NewsDigest>("/news/digest?limit=3");
      setNews(data);
    } catch { setError("Failed to fetch news."); }
    finally { setNewsLoading(false); }
  }

  useEffect(() => { void refreshOps(); }, []);
  useEffect(() => { if (activeTab === "habits") void refreshHabits(); }, [activeTab]);
  useEffect(() => { if (activeTab === "news" && !news) void loadNews(); }, [activeTab]);

  useEffect(() => {
    if ("Notification" in window && Notification.permission === "granted") setNotificationReady(true);
  }, []);

  useEffect(() => {
    if (!("Notification" in window)) return;
    const seen = new Set<number>();
    const tick = () => {
      const now = new Date();
      reminders.forEach((r) => {
        if (!r.due_at || seen.has(r.id)) return;
        if (r.due_at.startsWith("daily:")) {
          const [, hh, mm] = r.due_at.split(":");
          if (now.getHours() === Number(hh) && now.getMinutes() === Number(mm)) {
            if (Notification.permission === "granted") new Notification("VERONICA", { body: r.content });
            seen.add(r.id);
          }
        } else if (r.due_at.startsWith("once:")) {
          if (now >= new Date(r.due_at.slice(5))) {
            if (Notification.permission === "granted") new Notification("VERONICA", { body: r.content });
            seen.add(r.id);
          }
        }
      });
    };
    const iv = window.setInterval(tick, 30000);
    tick();
    return () => window.clearInterval(iv);
  }, [reminders]);

  const post = (path: string, body: object) =>
    fetch(`${API_URL}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

  const del = (path: string) => fetch(`${API_URL}${path}`, { method: "DELETE" });
  const patch = (path: string, body: object) =>
    fetch(`${API_URL}${path}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

  async function createTask() {
    const t = taskInput.trim(); if (!t) return;
    setBusy("task");
    try { await post("/tasks", { description: t, priority: "medium" }); setTaskInput(""); await refreshOps(); }
    catch { setError("Failed to create task."); } finally { setBusy(null); }
  }

  async function createNote() {
    const t = noteInput.trim(); if (!t) return;
    setBusy("note");
    try { await post("/notes", { content: t }); setNoteInput(""); await refreshOps(); }
    catch { setError("Failed to save note."); } finally { setBusy(null); }
  }

  async function createReminder() {
    const t = reminderInput.trim(); if (!t) return;
    setBusy("reminder");
    try { await post("/reminders", { content: t }); setReminderInput(""); await refreshOps(); }
    catch { setError("Failed to set reminder."); } finally { setBusy(null); }
  }

  async function createHabit() {
    const t = habitInput.trim(); if (!t) return;
    setBusy("habit");
    try { await post("/habits", { name: t }); setHabitInput(""); await refreshHabits(); }
    catch { setError("Failed to add habit."); } finally { setBusy(null); }
  }

  async function logHabit(id: number) {
    try { await post(`/habits/${id}/log`, {}); await refreshHabits(); }
    catch { setError("Failed to log habit."); }
  }

  const btn = "rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-3 py-1 text-xs text-[var(--accent-text)] hover:bg-[var(--accent)]/20 transition";
  const btnDanger = "rounded-lg border border-pink-300/30 px-2 py-1 text-xs text-pink-200 hover:bg-pink-400/10 transition";
  const input = "min-w-0 flex-1 rounded-lg border border-[var(--accent)]/20 bg-black/30 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500 focus:border-[var(--accent)]/50";

  return (
    <div className="space-y-4">
      {/* Tab bar */}
      <div className="flex gap-1 rounded-lg border border-white/10 bg-black/30 p-1 overflow-x-auto">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-shrink-0 rounded-md px-3 py-1.5 text-xs font-semibold transition ${
              activeTab === tab.id
                ? "bg-[var(--accent)]/20 text-[var(--accent-text)] border border-[var(--accent)]/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="flex items-center justify-between rounded-lg border border-pink-300/40 bg-pink-400/10 px-4 py-2 text-sm text-pink-200">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-4 text-xs text-pink-300">Dismiss</button>
        </div>
      )}

      {activeTab === "email"    && <EmailPanel />}
      {activeTab === "calendar" && <CalendarPanel />}
      {activeTab === "activity" && <ActivityPanel />}
      {activeTab === "github"   && <GitHubPanel />}
      {activeTab === "spotify"  && <SpotifyPanel />}
      {activeTab === "whatsapp" && <WhatsAppPanel />}

      {/* ── HABITS TAB ──────────────────────────────────────── */}
      {activeTab === "habits" && (
        <div className="hud-panel rounded-lg p-4">
          <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
            <Flame size={16} /> Habit Tracker
          </p>
          <div className="flex gap-2 mb-4">
            <input value={habitInput} onChange={(e) => setHabitInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void createHabit()}
              placeholder="New habit name" className={input} />
            <button onClick={() => void createHabit()} disabled={busy === "habit"}
              className={`${btn} px-4 py-2 disabled:opacity-50`}>Add</button>
          </div>
          {habits.length === 0 ? (
            <p className="text-sm text-slate-400">No habits yet. Add your first one above.</p>
          ) : (
            <div className="space-y-2">
              {habits.map((h) => (
                <div key={h.id} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 p-3">
                  <div className="flex items-center gap-3">
                    <div className="h-3 w-3 rounded-full flex-shrink-0" style={{ background: h.color }} />
                    <div>
                      <p className={`text-sm font-medium ${h.done_today ? "line-through text-slate-400" : "text-slate-100"}`}>{h.name}</p>
                      <p className="text-xs text-slate-500">
                        {h.streak > 0 ? `🔥 ${h.streak}-day streak` : "No streak yet"}
                        {" · "}{h.frequency}
                      </p>
                    </div>
                  </div>
                  <button onClick={() => void logHabit(h.id)} disabled={h.done_today}
                    className={`text-xs px-3 py-1 rounded-lg border transition ${
                      h.done_today
                        ? "border-emerald-400/40 text-emerald-300 bg-emerald-400/10 cursor-default"
                        : "border-[var(--accent)]/30 text-[var(--accent-text)] hover:bg-[var(--accent)]/20"
                    }`}>
                    {h.done_today ? "Done ✓" : "Mark done"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── NEWS TAB ────────────────────────────────────────── */}
      {activeTab === "news" && (
        <div className="hud-panel rounded-lg p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
              <Globe size={16} /> News Digest
            </p>
            <button onClick={() => void loadNews()} disabled={newsLoading} className={`${btn} disabled:opacity-50`}>
              {newsLoading ? "Fetching..." : "Refresh"}
            </button>
          </div>
          {newsLoading && <p className="text-sm text-slate-400 py-4 text-center">Fetching latest headlines…</p>}
          {!newsLoading && !news && <p className="text-sm text-slate-400">Click Refresh to load news.</p>}
          {news && (() => {
            // Group flat article list by feed_title
            const grouped = new Map<string, Article[]>();
            for (const a of news.feeds) {
              const key = a.feed_title ?? "General";
              if (!grouped.has(key)) grouped.set(key, []);
              grouped.get(key)!.push(a);
            }
            return (
              <div className="space-y-4">
                <p className="text-xs text-slate-500">{news.total} articles · {new Date(news.fetched_at).toLocaleTimeString()}</p>
                {Array.from(grouped.entries()).map(([feedTitle, articles], fi) => (
                  <div key={fi}>
                    <p className="text-xs uppercase tracking-widest text-slate-400 mb-2">{feedTitle}</p>
                    <div className="space-y-2">
                      {articles.slice(0, 3).map((a, ai) => (
                        <a key={ai} href={a.link} target="_blank" rel="noopener noreferrer"
                          className="block rounded-lg border border-white/10 bg-black/20 p-3 hover:border-[var(--accent)]/30 transition">
                          <p className="text-sm text-slate-100 leading-snug">{a.title}</p>
                          {a.summary && <p className="text-xs text-slate-400 mt-1 line-clamp-2">{a.summary}</p>}
                        </a>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            );
          })()}
        </div>
      )}

      {/* ── OPERATIONS TAB ──────────────────────────────────── */}
      {activeTab === "operations" && (
        <div className="grid gap-4 xl:grid-cols-2">
          {/* Daily Briefing */}
          <section className="hud-panel rounded-lg p-4">
            <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
              <CalendarClock size={16} /> Daily Briefing
            </p>
            <p className="text-sm text-slate-300">{briefing?.summary ?? "Loading briefing…"}</p>
            <p className="mt-3 rounded-lg border border-[var(--accent)]/20 bg-[var(--accent)]/[0.05] p-3 text-sm text-slate-100">
              {briefing?.focus_recommendation ?? "Stand by while I assemble the day."}
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div>
                <p className="mb-2 text-xs uppercase tracking-[0.18em] text-slate-400">Top Tasks</p>
                <div className="space-y-2">
                  {(briefing?.top_tasks ?? []).slice(0, 3).map((t) => (
                    <div key={t.id} className="rounded-lg border border-white/10 bg-black/20 p-2 text-sm text-slate-200">{t.description}</div>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-2 text-xs uppercase tracking-[0.18em] text-slate-400">Reminders</p>
                <div className="space-y-2">
                  {(briefing?.reminders ?? []).slice(0, 3).map((r) => (
                    <div key={r.id} className="rounded-lg border border-white/10 bg-black/20 p-2 text-sm text-slate-200">{r.content}</div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* Tasks */}
          <section className="hud-panel rounded-lg p-4">
            <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
              <CheckSquare size={16} /> Task Board
            </p>
            <div className="flex gap-2">
              <input value={taskInput} onChange={(e) => setTaskInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void createTask()}
                placeholder="Add task" className={input} />
              <button onClick={() => void createTask()} disabled={busy === "task"}
                className={`${btn} px-4 py-2 disabled:opacity-50`}>Add</button>
            </div>
            <div className="mt-4 space-y-2">
              {pendingTasks.slice(0, 6).map((t) => (
                <div key={t.id} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
                  <div>
                    <p className="text-slate-100">{t.description}</p>
                    <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{t.priority}</p>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => void patch(`/tasks/${t.id}`, { status: "done" }).then(refreshOps)} className={btn}>Done</button>
                    <button onClick={() => void del(`/tasks/${t.id}`).then(refreshOps)} className={btnDanger}>✕</button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Notes */}
          <section className="hud-panel rounded-lg p-4">
            <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
              <NotebookPen size={16} /> Notes
            </p>
            <div className="flex gap-2">
              <input value={noteInput} onChange={(e) => setNoteInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void createNote()}
                placeholder="Store a note" className={input} />
              <button onClick={() => void createNote()} disabled={busy === "note"}
                className={`${btn} px-4 py-2 disabled:opacity-50`}>Save</button>
            </div>
            <div className="mt-4 space-y-2">
              {notes.map((n) => (
                <div key={n.id} className="flex items-start justify-between gap-3 rounded-lg border border-white/10 bg-black/20 p-3 text-sm text-slate-200">
                  <span>{n.content}</span>
                  <button onClick={() => void del(`/notes/${n.id}`).then(refreshOps)} className={btnDanger}>✕</button>
                </div>
              ))}
            </div>
          </section>

          {/* Reminders */}
          <section className="hud-panel rounded-lg p-4">
            <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
              <TimerReset size={16} /> Reminders
            </p>
            <div className="mb-3 flex items-center justify-between gap-3">
              <p className="text-xs text-slate-400">
                {notificationReady ? "Alerts armed" : "Enable browser alerts for timed reminders"}
              </p>
              {!notificationReady && (
                <button onClick={() => Notification.requestPermission().then((p) => setNotificationReady(p === "granted"))}
                  className={btn}>Enable</button>
              )}
            </div>
            <div className="flex gap-2">
              <input value={reminderInput} onChange={(e) => setReminderInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void createReminder()}
                placeholder="Set reminder" className={input} />
              <button onClick={() => void createReminder()} disabled={busy === "reminder"}
                className={`${btn} px-4 py-2 disabled:opacity-50`}>Set</button>
            </div>
            <div className="mt-4 space-y-2">
              {reminders.map((r) => (
                <div key={r.id} className="flex items-start justify-between gap-3 rounded-lg border border-white/10 bg-black/20 p-3 text-sm text-slate-200">
                  <div>
                    <span>{r.content}</span>
                    {r.due_label && <p className="mt-1 text-xs uppercase tracking-[0.14em] text-slate-500">{r.due_label}</p>}
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => void patch(`/reminders/${r.id}`, { status: "done" }).then(refreshOps)} className={btn}>Done</button>
                    <button onClick={() => void del(`/reminders/${r.id}`).then(refreshOps)} className={btnDanger}>✕</button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
