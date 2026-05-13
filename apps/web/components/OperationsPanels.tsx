"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Activity, BookOpen, Check, Newspaper, Settings, Target, X,
} from "lucide-react";
import {
  SiGithub, SiGmail, SiGooglecalendar, SiSpotify, SiWhatsapp,
} from "react-icons/si";
import { ActivityPanel } from "@/components/ActivityPanel";
import { CalendarPanel } from "@/components/CalendarPanel";
import { EmailPanel } from "@/components/EmailPanel";
import { GitHubPanel } from "@/components/GitHubPanel";
import JournalPanel from "@/components/JournalPanel";
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

type Tab = "operations" | "habits" | "news" | "email" | "calendar" | "activity" | "github" | "spotify" | "whatsapp" | "journal";

type TabDef = { id: Tab; label: string; short: string; icon: React.ReactNode };

const TABS: TabDef[] = [
  { id: "operations", label: "Operations", short: "OPS",  icon: <Settings   size={13} /> },
  { id: "habits",     label: "Habits",     short: "HBT",  icon: <Target     size={13} /> },
  { id: "news",       label: "News",       short: "NWS",  icon: <Newspaper  size={13} /> },
  { id: "email",      label: "Mail",       short: "MAIL", icon: <SiGmail    size={13} /> },
  { id: "calendar",   label: "Calendar",   short: "CAL",  icon: <SiGooglecalendar size={13} /> },
  { id: "activity",   label: "Activity",   short: "ACT",  icon: <Activity   size={13} /> },
  { id: "github",     label: "GitHub",     short: "GH",   icon: <SiGithub   size={13} /> },
  { id: "spotify",    label: "Spotify",    short: "SPT",  icon: <SiSpotify  size={13} /> },
  { id: "whatsapp",   label: "WhatsApp",   short: "WA",   icon: <SiWhatsapp size={13} /> },
  { id: "journal",    label: "Journal",    short: "LOG",  icon: <BookOpen   size={13} /> },
];

/* ── Priority badge ──────────────────────────────────────── */
function PriBadge({ pri }: { pri: string }) {
  const cls =
    pri === "high"   ? "tool-pill crit" :
    pri === "medium" ? "tool-pill warn" :
    "tool-pill";
  const label = pri === "high" ? "P1" : pri === "medium" ? "P2" : "P3";
  return <span className={cls}>{label}</span>;
}

export function OperationsPanels() {
  const [activeTab, setActiveTab] = useState<Tab>("operations");
  const [briefing, setBriefing]   = useState<Briefing | null>(null);
  const [tasks, setTasks]         = useState<Task[]>([]);
  const [notes, setNotes]         = useState<Note[]>([]);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [habits, setHabits]       = useState<Habit[]>([]);
  const [news, setNews]           = useState<NewsDigest | null>(null);
  const [newsLoading, setNewsLoading] = useState(false);

  const [taskInput, setTaskInput]         = useState("");
  const [noteInput, setNoteInput]         = useState("");
  const [reminderInput, setReminderInput] = useState("");
  const [habitInput, setHabitInput]       = useState("");

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

  const post  = (path: string, body: object) =>
    fetch(`${API_URL}${path}`, { method: "POST",  headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const del   = (path: string) =>
    fetch(`${API_URL}${path}`, { method: "DELETE" });
  const patch = (path: string, body: object) =>
    fetch(`${API_URL}${path}`, { method: "PATCH",  headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

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

  const activeLabel = TABS.find((t) => t.id === activeTab)?.label ?? "";

  return (
    <div className="hud-panel rounded-lg overflow-hidden">
      {/* ── Panel header ─────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--accent)]/15">
        <span className="text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: "var(--accent-text)" }}>
          🛠️ Tool Surfaces · {activeLabel}
        </span>
        <span className="text-[9px] font-mono tracking-[0.15em] text-slate-600">
          {TABS.length} tools
        </span>
      </div>

      {/* ── Tab rail ─────────────────────────────────────── */}
      <div className="tools-rail" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={activeTab === t.id}
            className={`tools-tab ${activeTab === t.id ? "active" : ""}`}
            onClick={() => setActiveTab(t.id)}
            title={t.label}
          >
            <span className="tools-glyph">{t.icon}</span>
            <span className="tools-tablabel">{t.short}</span>
          </button>
        ))}
      </div>

      {/* ── Error banner ─────────────────────────────────── */}
      {error && (
        <div className="mx-4 mt-3 flex items-center justify-between rounded border border-pink-300/30 bg-pink-400/8 px-3 py-2 text-xs text-pink-300">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-pink-400 hover:text-pink-200 transition ml-3">
            <X size={10} />
          </button>
        </div>
      )}

      {/* ── Delegated panels ─────────────────────────────── */}
      <div className="p-4">
        {activeTab === "email"    && <EmailPanel />}
        {activeTab === "calendar" && <CalendarPanel />}
        {activeTab === "activity" && <ActivityPanel />}
        {activeTab === "github"   && <GitHubPanel />}
        {activeTab === "spotify"  && <SpotifyPanel />}
        {activeTab === "whatsapp" && <WhatsAppPanel />}
        {activeTab === "journal"  && <JournalPanel />}
      </div>

      {/* ── Habits ───────────────────────────────────────── */}
      {activeTab === "habits" && (
        <div>
          <div className="tool-header">
            <div>
              <div className="tool-title">🎯 Habit Tracker</div>
              <div className="tool-sub">{habits.filter((h) => h.done_today).length}/{habits.length} today · habit_status</div>
            </div>
            <button
              onClick={() => void createHabit()}
              disabled={busy === "habit"}
              className="tool-action"
            >
              + Add
            </button>
          </div>

          <div className="px-3 pb-2 pt-1">
            <input
              value={habitInput}
              onChange={(e) => setHabitInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void createHabit()}
              placeholder="new habit name"
              className="tool-input"
            />
          </div>

          {habits.length === 0 ? (
            <div className="tool-empty">No habits yet. Add your first one above.</div>
          ) : (
            <div className="tool-list">
              {habits.map((h) => (
                <div key={h.id} className="habit-row">
                  <button
                    onClick={() => void logHabit(h.id)}
                    disabled={h.done_today}
                    className={`habit-tick ${h.done_today ? "done" : ""}`}
                    aria-label={`Log ${h.name}`}
                  >
                    {h.done_today ? <Check size={9} /> : ""}
                  </button>
                  <div className="habit-body">
                    <div className={`habit-name ${h.done_today ? "line-through opacity-50" : ""}`}>{h.name}</div>
                    <div className="habit-meta">
                      {h.streak > 0 ? `${h.streak}-day streak` : "no streak"} · {h.frequency}
                    </div>
                  </div>
                  <div
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ background: h.color, opacity: 0.8 }}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── News ─────────────────────────────────────────── */}
      {activeTab === "news" && (
        <div>
          <div className="tool-header">
            <div>
              <div className="tool-title">📰 News Digest</div>
              <div className="tool-sub">
                {news ? `${news.total} articles · ${new Date(news.fetched_at).toLocaleTimeString()}` : "click refresh to load"}
              </div>
            </div>
            <button onClick={() => void loadNews()} disabled={newsLoading} className="tool-action">
              {newsLoading ? "…" : "Refresh"}
            </button>
          </div>

          {newsLoading && <div className="tool-empty">Fetching headlines…</div>}
          {!newsLoading && !news && <div className="tool-empty">No digest loaded.</div>}

          {news && (() => {
            const grouped = new Map<string, Article[]>();
            for (const a of news.feeds) {
              const key = a.feed_title ?? "General";
              if (!grouped.has(key)) grouped.set(key, []);
              grouped.get(key)!.push(a);
            }
            return (
              <div className="tool-list">
                {Array.from(grouped.entries()).map(([feedTitle, articles], fi) => (
                  <div key={fi}>
                    <div className="divlabel-sm">{feedTitle}</div>
                    {articles.slice(0, 3).map((a, ai) => (
                      <a
                        key={ai}
                        href={a.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="tool-row clickable block"
                      >
                        <div className="tool-row-main">
                          <div className="tool-row-left text-slate-200 text-xs">{a.title}</div>
                          {a.summary && <div className="tool-row-sub">{a.summary}</div>}
                        </div>
                        <span className="tool-row-meta shrink-0">→</span>
                      </a>
                    ))}
                  </div>
                ))}
              </div>
            );
          })()}
        </div>
      )}

      {/* ── Operations (2×2 grid) ────────────────────────── */}
      {activeTab === "operations" && (
        <div className="grid gap-3 p-3 xl:grid-cols-2">

          {/* Daily Briefing */}
          <section className="rounded-lg border border-white/[0.07] bg-black/20 overflow-hidden">
            <div className="tool-header">
              <div>
                <div className="tool-title">🗂️ Daily Briefing</div>
                <div className="tool-sub">
                  {briefing
                    ? `${briefing.top_tasks.length} task(s) · ${briefing.reminders.length} reminder(s)`
                    : "loading…"}
                </div>
              </div>
            </div>
            <div className="px-3 pb-3 pt-2 space-y-2">
              <p className="text-xs text-slate-300 leading-relaxed">
                {briefing?.summary ?? "Assembling the day…"}
              </p>
              <p className="rounded border border-[var(--accent)]/15 bg-[var(--accent)]/[0.05] px-3 py-2 text-xs text-slate-200 leading-relaxed">
                {briefing?.focus_recommendation ?? "Stand by."}
              </p>
              {(briefing?.top_tasks?.length ?? 0) > 0 && (
                <>
                  <div className="divlabel-sm" style={{ padding: "4px 0 2px" }}>Top Tasks</div>
                  {briefing!.top_tasks.slice(0, 3).map((t) => (
                    <div key={t.id} className="flex items-center gap-2 text-xs text-slate-300 py-0.5">
                      <span className="text-[11px]">📌</span>
                      <span className="truncate">{t.description}</span>
                    </div>
                  ))}
                </>
              )}
              {(briefing?.reminders?.length ?? 0) > 0 && (
                <>
                  <div className="divlabel-sm" style={{ padding: "4px 0 2px" }}>Reminders</div>
                  {briefing!.reminders.slice(0, 2).map((r) => (
                    <div key={r.id} className="flex items-center gap-2 text-xs text-slate-400 py-0.5">
                      <span className="text-[11px]">🔔</span>
                      <span className="truncate">{r.content}</span>
                    </div>
                  ))}
                </>
              )}
            </div>
          </section>

          {/* Task Board */}
          <section className="rounded-lg border border-white/[0.07] bg-black/20 overflow-hidden">
            <div className="tool-header">
              <div>
                <div className="tool-title">✅ Task Board</div>
                <div className="tool-sub">{pendingTasks.length} pending · task_list</div>
              </div>
            </div>

            <div className="tool-compose" style={{ borderTop: "none", paddingBottom: 0 }}>
              <div className="flex gap-1.5">
                <input
                  value={taskInput}
                  onChange={(e) => setTaskInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && void createTask()}
                  placeholder="add task"
                  className="tool-input"
                />
                <button
                  onClick={() => void createTask()}
                  disabled={busy === "task"}
                  className="tool-btn"
                  style={{ whiteSpace: "nowrap" }}
                >
                  Add
                </button>
              </div>
            </div>

            <div className="tool-list">
              {pendingTasks.slice(0, 6).map((t) => (
                <div key={t.id} className="habit-row">
                  <button
                    onClick={() => void patch(`/tasks/${t.id}`, { status: "done" }).then(refreshOps)}
                    className="habit-tick"
                    aria-label="Mark done"
                  />
                  <div className="habit-body">
                    <div className="habit-name truncate">{t.description}</div>
                    <div className="habit-meta">{t.priority} priority</div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <PriBadge pri={t.priority} />
                    <button
                      onClick={() => void del(`/tasks/${t.id}`).then(refreshOps)}
                      className="text-slate-600 hover:text-pink-300 transition ml-1"
                    >
                      <X size={9} />
                    </button>
                  </div>
                </div>
              ))}
              {pendingTasks.length === 0 && (
                <div className="tool-empty">No pending tasks.</div>
              )}
            </div>
          </section>

          {/* Notes */}
          <section className="rounded-lg border border-white/[0.07] bg-black/20 overflow-hidden">
            <div className="tool-header">
              <div>
                <div className="tool-title">📝 Notes</div>
                <div className="tool-sub">{notes.length} saved · notes_store</div>
              </div>
            </div>

            <div className="tool-compose" style={{ borderTop: "none", paddingBottom: 0 }}>
              <div className="flex gap-1.5">
                <input
                  value={noteInput}
                  onChange={(e) => setNoteInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && void createNote()}
                  placeholder="store a note"
                  className="tool-input"
                />
                <button
                  onClick={() => void createNote()}
                  disabled={busy === "note"}
                  className="tool-btn"
                >
                  Save
                </button>
              </div>
            </div>

            <div className="tool-list">
              {notes.map((n) => (
                <div key={n.id} className="tool-row">
                  <div className="tool-row-main">
                    <div className="tool-row-left">
                      <span className="text-[11px] shrink-0">📝</span>
                      <span className="text-xs text-slate-200 break-words min-w-0">{n.content}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => void del(`/notes/${n.id}`).then(refreshOps)}
                    className="text-slate-600 hover:text-pink-300 transition shrink-0 ml-2"
                  >
                    <X size={9} />
                  </button>
                </div>
              ))}
              {notes.length === 0 && <div className="tool-empty">No notes yet.</div>}
            </div>
          </section>

          {/* Reminders */}
          <section className="rounded-lg border border-white/[0.07] bg-black/20 overflow-hidden">
            <div className="tool-header">
              <div>
                <div className="tool-title">🔔 Reminders</div>
                <div className="tool-sub">
                  {notificationReady ? "alerts armed" : "enable browser alerts"}
                </div>
              </div>
              {!notificationReady && (
                <button
                  onClick={() => Notification.requestPermission().then((p) => setNotificationReady(p === "granted"))}
                  className="tool-action"
                >
                  Enable
                </button>
              )}
            </div>

            <div className="tool-compose" style={{ borderTop: "none", paddingBottom: 0 }}>
              <div className="flex gap-1.5">
                <input
                  value={reminderInput}
                  onChange={(e) => setReminderInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && void createReminder()}
                  placeholder="set reminder"
                  className="tool-input"
                />
                <button
                  onClick={() => void createReminder()}
                  disabled={busy === "reminder"}
                  className="tool-btn"
                >
                  Set
                </button>
              </div>
            </div>

            <div className="tool-list">
              {reminders.map((r) => (
                <div key={r.id} className="tool-row">
                  <div className="tool-row-main">
                    <div className="tool-row-left">
                      <span className="text-[11px] shrink-0">🔔</span>
                      <span className="text-xs text-slate-200 break-words min-w-0">{r.content}</span>
                    </div>
                    {r.due_label && (
                      <div className="tool-row-sub">{r.due_label}</div>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0 ml-2">
                    <button
                      onClick={() => void patch(`/reminders/${r.id}`, { status: "done" }).then(refreshOps)}
                      className="tool-pill ok cursor-pointer hover:bg-emerald-400/20 transition"
                    >
                      DONE
                    </button>
                    <button
                      onClick={() => void del(`/reminders/${r.id}`).then(refreshOps)}
                      className="text-slate-600 hover:text-pink-300 transition"
                    >
                      <X size={9} />
                    </button>
                  </div>
                </div>
              ))}
              {reminders.length === 0 && <div className="tool-empty">No reminders set.</div>}
            </div>
          </section>

        </div>
      )}
    </div>
  );
}
