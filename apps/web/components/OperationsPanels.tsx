"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarClock, CheckSquare, NotebookPen, TimerReset } from "lucide-react";
import { ActivityPanel } from "@/components/ActivityPanel";
import { CalendarPanel } from "@/components/CalendarPanel";
import { EmailPanel } from "@/components/EmailPanel";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Task = {
  id: number;
  description: string;
  priority: string;
  status: string;
};

type Note = {
  id: number;
  content: string;
  created_at: string;
};

type Reminder = {
  id: number;
  content: string;
  due_at: string | null;
  due_label?: string | null;
  status: string;
};

type Briefing = {
  summary: string;
  focus_recommendation: string;
  top_tasks: Task[];
  reminders: Reminder[];
};

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch ${path}`);
  return response.json();
}

type Tab = "operations" | "email" | "calendar" | "activity";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "operations", label: "Operations" },
  { id: "email",      label: "Mail" },
  { id: "calendar",   label: "Calendar" },
  { id: "activity",   label: "Activity" },
];

export function OperationsPanels() {
  const [activeTab, setActiveTab] = useState<Tab>("operations");
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [taskInput, setTaskInput] = useState("");
  const [noteInput, setNoteInput] = useState("");
  const [reminderInput, setReminderInput] = useState("");
  const [busy, setBusy] = useState<null | "task" | "note" | "reminder">(null);
  const [error, setError] = useState<string | null>(null);
  const [notificationReady, setNotificationReady] = useState(false);

  const pendingTasks = useMemo(() => tasks.filter((task) => task.status === "pending"), [tasks]);

  async function refreshAll() {
    try {
      const [briefingData, taskData, noteData, reminderData] = await Promise.all([
        fetchJson<Briefing>("/briefing/today"),
        fetchJson<{ items: Task[] }>("/tasks?limit=6"),
        fetchJson<{ items: Note[] }>("/notes?limit=4"),
        fetchJson<{ items: Reminder[] }>("/reminders?limit=4"),
      ]);
      setBriefing(briefingData);
      setTasks(taskData.items);
      setNotes(noteData.items);
      setReminders(reminderData.items);
      setError(null);
    } catch {
      setError("Failed to load data. Is the API running on port 8000?");
    }
  }

  useEffect(() => {
    void refreshAll();
  }, []);

  useEffect(() => {
    if ("Notification" in window && Notification.permission === "granted") {
      setNotificationReady(true);
    }
  }, []);

  useEffect(() => {
    if (!("Notification" in window)) return;

    const seen = new Set<number>();
    const tick = () => {
      const now = new Date();
      reminders.forEach((reminder) => {
        if (!reminder.due_at || seen.has(reminder.id)) return;

        if (reminder.due_at.startsWith("daily:")) {
          const [, hh, mm] = reminder.due_at.split(":");
          if (now.getHours() === Number(hh) && now.getMinutes() === Number(mm)) {
            if (Notification.permission === "granted") {
              new Notification("VERONICA Reminder", { body: reminder.content });
            }
            seen.add(reminder.id);
          }
          return;
        }

        if (reminder.due_at.startsWith("once:")) {
          const due = new Date(reminder.due_at.slice(5));
          if (now >= due) {
            if (Notification.permission === "granted") {
              new Notification("VERONICA Reminder", { body: reminder.content });
            }
            seen.add(reminder.id);
          }
        }
      });
    };

    const interval = window.setInterval(tick, 30000);
    tick();
    return () => window.clearInterval(interval);
  }, [reminders]);

  async function enableNotifications() {
    if (!("Notification" in window)) return;
    const permission = await Notification.requestPermission();
    setNotificationReady(permission === "granted");
  }

  async function createTask() {
    const trimmed = taskInput.trim();
    if (!trimmed) return;
    setBusy("task");
    try {
      const res = await fetch(`${API_URL}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: trimmed, priority: "medium" }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setTaskInput("");
      await refreshAll();
    } catch {
      setError("Failed to create task. API may be offline.");
    } finally {
      setBusy(null);
    }
  }

  async function createNote() {
    const trimmed = noteInput.trim();
    if (!trimmed) return;
    setBusy("note");
    try {
      const res = await fetch(`${API_URL}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: trimmed }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setNoteInput("");
      await refreshAll();
    } catch {
      setError("Failed to save note. API may be offline.");
    } finally {
      setBusy(null);
    }
  }

  async function createReminder() {
    const trimmed = reminderInput.trim();
    if (!trimmed) return;
    setBusy("reminder");
    try {
      const res = await fetch(`${API_URL}/reminders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: trimmed }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setReminderInput("");
      await refreshAll();
    } catch {
      setError("Failed to set reminder. API may be offline.");
    } finally {
      setBusy(null);
    }
  }

  async function completeTask(taskId: number) {
    try {
      const res = await fetch(`${API_URL}/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "done" }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await refreshAll();
    } catch {
      setError("Failed to complete task.");
    }
  }

  async function deleteTask(taskId: number) {
    try {
      const res = await fetch(`${API_URL}/tasks/${taskId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await refreshAll();
    } catch {
      setError("Failed to delete task.");
    }
  }

  async function completeReminder(reminderId: number) {
    try {
      const res = await fetch(`${API_URL}/reminders/${reminderId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "done" }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await refreshAll();
    } catch {
      setError("Failed to complete reminder.");
    }
  }

  async function deleteReminder(reminderId: number) {
    try {
      const res = await fetch(`${API_URL}/reminders/${reminderId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await refreshAll();
    } catch {
      setError("Failed to delete reminder.");
    }
  }

  async function deleteNote(noteId: number) {
    try {
      const res = await fetch(`${API_URL}/notes/${noteId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await refreshAll();
    } catch {
      setError("Failed to delete note.");
    }
  }

  return (
    <div className="space-y-4">
      {/* Tab bar */}
      <div className="flex gap-1 rounded-lg border border-white/10 bg-black/30 p-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 rounded-md py-1.5 text-xs font-semibold transition ${
              activeTab === tab.id
                ? "bg-[var(--accent)]/20 text-[var(--accent-text)] border border-[var(--accent)]/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "email" && <EmailPanel />}
      {activeTab === "calendar" && <CalendarPanel />}
      {activeTab === "activity" && <ActivityPanel />}

      {activeTab === "operations" && (
      <>
      {error ? (
        <div className="flex items-center justify-between rounded-lg border border-pink-300/40 bg-pink-400/10 px-4 py-2 text-sm text-pink-200">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-4 text-xs text-pink-300 hover:text-pink-100">
            Dismiss
          </button>
        </div>
      ) : null}
    <div className="grid gap-4 xl:grid-cols-2">
      <section className="hud-panel rounded-lg p-4">
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-cyan-100">
          <CalendarClock size={16} /> Daily Briefing
        </p>
        <p className="text-sm text-slate-300">{briefing?.summary ?? "Loading briefing..."}</p>
        <p className="mt-3 rounded-lg border border-cyan-300/20 bg-cyan-300/[0.05] p-3 text-sm text-cyan-50">
          {briefing?.focus_recommendation ?? "Stand by while I assemble the day."}
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div>
            <p className="mb-2 text-xs uppercase tracking-[0.18em] text-slate-400">Top Tasks</p>
            <div className="space-y-2">
              {(briefing?.top_tasks ?? []).slice(0, 3).map((task) => (
                <div key={task.id} className="rounded-lg border border-white/10 bg-black/20 p-2 text-sm text-slate-200">
                  {task.description}
                </div>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-2 text-xs uppercase tracking-[0.18em] text-slate-400">Reminders</p>
            <div className="space-y-2">
              {(briefing?.reminders ?? []).slice(0, 3).map((reminder) => (
                <div key={reminder.id} className="rounded-lg border border-white/10 bg-black/20 p-2 text-sm text-slate-200">
                  {reminder.content}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="hud-panel rounded-lg p-4">
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-cyan-100">
          <CheckSquare size={16} /> Task Board
        </p>
        <div className="flex gap-2">
          <input
            value={taskInput}
            onChange={(event) => setTaskInput(event.target.value)}
            placeholder="Add task"
            className="min-w-0 flex-1 rounded-lg border border-cyan-300/20 bg-black/30 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500"
          />
          <button
            onClick={() => void createTask()}
            disabled={busy === "task"}
            className="rounded-lg border border-cyan-300/40 bg-cyan-300/15 px-4 py-2 text-sm text-cyan-50 disabled:opacity-50"
          >
            Add
          </button>
        </div>
        <div className="mt-4 space-y-2">
          {pendingTasks.slice(0, 6).map((task) => (
            <div key={task.id} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
              <div>
                <p className="text-slate-100">{task.description}</p>
                <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{task.priority}</p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => void completeTask(task.id)}
                  className="rounded-lg border border-cyan-300/30 px-3 py-1 text-xs text-cyan-100"
                >
                  Done
                </button>
                <button
                  onClick={() => void deleteTask(task.id)}
                  className="rounded-lg border border-pink-300/30 px-3 py-1 text-xs text-pink-100"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="hud-panel rounded-lg p-4">
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-cyan-100">
          <NotebookPen size={16} /> Notes Memory
        </p>
        <div className="flex gap-2">
          <input
            value={noteInput}
            onChange={(event) => setNoteInput(event.target.value)}
            placeholder="Store a note"
            className="min-w-0 flex-1 rounded-lg border border-cyan-300/20 bg-black/30 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500"
          />
          <button
            onClick={() => void createNote()}
            disabled={busy === "note"}
            className="rounded-lg border border-cyan-300/40 bg-cyan-300/15 px-4 py-2 text-sm text-cyan-50 disabled:opacity-50"
          >
            Save
          </button>
        </div>
        <div className="mt-4 space-y-2">
          {notes.map((note) => (
            <div key={note.id} className="flex items-start justify-between gap-3 rounded-lg border border-white/10 bg-black/20 p-3 text-sm text-slate-200">
              <span>{note.content}</span>
              <button
                onClick={() => void deleteNote(note.id)}
                className="rounded-lg border border-pink-300/30 px-2 py-1 text-xs text-pink-100"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="hud-panel rounded-lg p-4">
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-cyan-100">
          <TimerReset size={16} /> Reminders
        </p>
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-xs text-slate-400">
            {notificationReady ? "Reminder alerts armed" : "Enable browser notifications for timed alerts"}
          </p>
          {!notificationReady ? (
            <button
              onClick={() => void enableNotifications()}
              className="rounded-lg border border-cyan-300/30 px-3 py-1 text-xs text-cyan-100"
            >
              Enable alerts
            </button>
          ) : null}
        </div>
        <div className="flex gap-2">
          <input
            value={reminderInput}
            onChange={(event) => setReminderInput(event.target.value)}
            placeholder="Set reminder"
            className="min-w-0 flex-1 rounded-lg border border-cyan-300/20 bg-black/30 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500"
          />
          <button
            onClick={() => void createReminder()}
            disabled={busy === "reminder"}
            className="rounded-lg border border-cyan-300/40 bg-cyan-300/15 px-4 py-2 text-sm text-cyan-50 disabled:opacity-50"
          >
            Set
          </button>
        </div>
        <div className="mt-4 space-y-2">
          {reminders.map((reminder) => (
            <div key={reminder.id} className="flex items-start justify-between gap-3 rounded-lg border border-white/10 bg-black/20 p-3 text-sm text-slate-200">
              <div>
                <span>{reminder.content}</span>
                {reminder.due_label ? (
                  <p className="mt-1 text-xs uppercase tracking-[0.14em] text-slate-500">{reminder.due_label}</p>
                ) : null}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => void completeReminder(reminder.id)}
                  className="rounded-lg border border-cyan-300/30 px-2 py-1 text-xs text-cyan-100"
                >
                  Done
                </button>
                <button
                  onClick={() => void deleteReminder(reminder.id)}
                  className="rounded-lg border border-pink-300/30 px-2 py-1 text-xs text-pink-100"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
      </>
      )}
    </div>
  );
}
