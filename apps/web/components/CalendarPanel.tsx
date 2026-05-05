"use client";

import { Calendar, Clock, Plus, RefreshCw, Users, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type CalEvent = {
  id: string;
  title: string;
  start: string;
  end: string;
  description: string;
  attendees: string[];
  meet_link: string;
  all_day: boolean;
};

type FreeSlot = { start: string; end: string; label: string };

type OAuthStatus = { google_configured: boolean; calendar: boolean };

type MeetingForm = {
  title: string;
  start: string;
  end: string;
  description: string;
  attendees: string;
};

function formatEventTime(iso: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function isToday(iso: string): boolean {
  try {
    const d = new Date(iso);
    const now = new Date();
    return d.toDateString() === now.toDateString();
  } catch {
    return false;
  }
}

export function CalendarPanel() {
  const [status, setStatus] = useState<OAuthStatus | null>(null);
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [freeSlots, setFreeSlots] = useState<FreeSlot[]>([]);
  const [loading, setLoading] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [showFree, setShowFree] = useState(false);
  const [form, setForm] = useState<MeetingForm>({
    title: "",
    start: "",
    end: "",
    description: "",
    attendees: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/oauth/status`);
      setStatus((await res.json()) as OAuthStatus);
    } catch {
      setStatus({ google_configured: false, calendar: false });
    }
  }, []);

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/calendar/events?days=7`);
      const data = await res.json();
      if (data.ok) setEvents(data.result as CalEvent[]);
      else setError(data.error ?? "Failed to load events");
    } catch {
      setError("Cannot reach API");
    } finally {
      setLoading(false);
    }
  }, []);

  async function fetchFreeSlots() {
    setShowFree(true);
    try {
      const res = await fetch(`${API}/calendar/freebusy?duration=60&days=7`);
      const data = await res.json();
      if (data.ok) setFreeSlots(data.result as FreeSlot[]);
    } catch {
      setError("Failed to fetch free slots");
    }
  }

  async function createEvent() {
    if (!form.title || !form.start || !form.end) return;
    setScheduling(true);
    setError(null);
    try {
      const res = await fetch(`${API}/calendar/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: form.title,
          start: form.start,
          end: form.end,
          description: form.description,
          attendees: form.attendees
            ? form.attendees.split(",").map((e) => e.trim()).filter(Boolean)
            : [],
        }),
      });
      const data = await res.json();
      if (data.ok) {
        setSuccessMsg(`Meeting "${form.title}" scheduled!${data.result?.meet_link ? " Meet link created." : ""}`);
        setShowForm(false);
        setForm({ title: "", start: "", end: "", description: "", attendees: "" });
        void fetchEvents();
      } else {
        setError(data.error ?? "Failed to create event");
      }
    } catch {
      setError("API error");
    } finally {
      setScheduling(false);
    }
  }

  function slotToForm(slot: FreeSlot) {
    const endDt = new Date(new Date(slot.start).getTime() + 60 * 60 * 1000);
    setForm((f) => ({
      ...f,
      start: new Date(slot.start).toISOString().slice(0, 16),
      end: endDt.toISOString().slice(0, 16),
    }));
    setShowFree(false);
    setShowForm(true);
  }

  useEffect(() => { void fetchStatus(); }, [fetchStatus]);
  useEffect(() => { if (status?.calendar) void fetchEvents(); }, [status, fetchEvents]);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected") === "google") void fetchStatus();
  }, [fetchStatus]);

  if (!status) return (
    <div className="hud-panel rounded-lg p-4 text-sm text-slate-400">
      <p className="flex items-center gap-2 font-semibold" style={{ color: "var(--accent-text)" }}>
        <Calendar size={16} /> Calendar
      </p>
      <p className="mt-3">Loading...</p>
    </div>
  );

  if (!status.google_configured) return (
    <div className="hud-panel rounded-lg p-4">
      <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
        <Calendar size={16} /> Calendar
      </p>
      <p className="text-xs text-slate-400">
        Add <code className="text-cyan-300">GOOGLE_CLIENT_ID</code> and{" "}
        <code className="text-cyan-300">GOOGLE_CLIENT_SECRET</code> to <code className="text-cyan-300">apps/api/.env</code> to enable Calendar.
      </p>
    </div>
  );

  if (!status.calendar) return (
    <div className="hud-panel rounded-lg p-4">
      <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
        <Calendar size={16} /> Calendar
      </p>
      <p className="mb-4 text-xs text-slate-400">Connect Google Calendar to schedule meetings and view your agenda.</p>
      <a
        href={`${API}/oauth/google/start`}
        className="inline-block rounded-lg border border-[var(--accent)]/40 bg-[var(--accent)]/15 px-4 py-2 text-sm font-semibold text-[var(--accent-text)] hover:bg-[var(--accent)]/25 transition"
      >
        Connect Google Calendar
      </a>
    </div>
  );

  return (
    <div className="hud-panel rounded-lg p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <Calendar size={16} /> Calendar
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => void fetchFreeSlots()}
            className="rounded border border-white/10 px-2 py-1 text-[10px] text-slate-400 hover:text-white transition"
          >
            Find free slot
          </button>
          <button
            onClick={() => setShowForm(true)}
            className="rounded border border-[var(--accent)]/30 px-2 py-1 text-[10px] text-[var(--accent-text)] hover:bg-[var(--accent)]/10 transition flex items-center gap-1"
          >
            <Plus size={10} /> Schedule
          </button>
          <button onClick={() => void fetchEvents()} disabled={loading} className="rounded border border-white/10 p-1 text-slate-400 hover:text-white transition disabled:opacity-40">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-2 flex items-center justify-between rounded border border-pink-300/30 bg-pink-400/10 px-3 py-2 text-xs text-pink-200">
          <span>{error}</span>
          <button onClick={() => setError(null)}><X size={12} /></button>
        </div>
      )}

      {successMsg && (
        <div className="mb-2 rounded border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-200 flex items-center justify-between">
          <span>{successMsg}</span>
          <button onClick={() => setSuccessMsg(null)}><X size={12} /></button>
        </div>
      )}

      {showFree && freeSlots.length > 0 && (
        <div className="mb-3 rounded-lg border border-white/10 bg-black/20 p-3">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-xs font-semibold text-slate-300">Available 60-min slots</p>
            <button onClick={() => setShowFree(false)}><X size={12} className="text-slate-400" /></button>
          </div>
          <div className="space-y-1.5">
            {freeSlots.map((slot) => (
              <button
                key={slot.start}
                onClick={() => slotToForm(slot)}
                className="w-full rounded border border-white/10 bg-black/20 px-3 py-2 text-left text-xs text-slate-200 hover:border-[var(--accent)]/40 hover:bg-[var(--accent)]/5 transition"
              >
                <Clock size={10} className="inline mr-1.5 text-slate-400" />
                {slot.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {showForm && (
        <div className="mb-3 rounded-lg border border-[var(--accent)]/30 bg-black/30 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[var(--accent-text)]">Schedule Meeting</span>
            <button onClick={() => setShowForm(false)}><X size={12} className="text-slate-400" /></button>
          </div>
          <input
            placeholder="Meeting title"
            value={form.title}
            onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            className="w-full rounded border border-white/10 bg-black/40 px-3 py-1.5 text-xs text-white outline-none placeholder:text-slate-500 focus:border-[var(--accent-strong)]"
          />
          <div className="grid grid-cols-2 gap-2">
            <div>
              <p className="text-[10px] text-slate-500 mb-1">Start</p>
              <input
                type="datetime-local"
                value={form.start}
                onChange={(e) => setForm((f) => ({ ...f, start: e.target.value }))}
                className="w-full rounded border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-white outline-none focus:border-[var(--accent-strong)]"
              />
            </div>
            <div>
              <p className="text-[10px] text-slate-500 mb-1">End</p>
              <input
                type="datetime-local"
                value={form.end}
                onChange={(e) => setForm((f) => ({ ...f, end: e.target.value }))}
                className="w-full rounded border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-white outline-none focus:border-[var(--accent-strong)]"
              />
            </div>
          </div>
          <input
            placeholder="Attendees (comma-separated emails)"
            value={form.attendees}
            onChange={(e) => setForm((f) => ({ ...f, attendees: e.target.value }))}
            className="w-full rounded border border-white/10 bg-black/40 px-3 py-1.5 text-xs text-white outline-none placeholder:text-slate-500 focus:border-[var(--accent-strong)]"
          />
          <input
            placeholder="Description (optional)"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            className="w-full rounded border border-white/10 bg-black/40 px-3 py-1.5 text-xs text-white outline-none placeholder:text-slate-500 focus:border-[var(--accent-strong)]"
          />
          <button
            onClick={() => void createEvent()}
            disabled={scheduling || !form.title || !form.start || !form.end}
            className="flex items-center gap-2 rounded border border-[var(--accent)]/40 bg-[var(--accent)]/15 px-4 py-1.5 text-xs font-semibold text-[var(--accent-text)] disabled:opacity-40 hover:bg-[var(--accent)]/25 transition"
          >
            <Calendar size={12} /> {scheduling ? "Scheduling..." : "Create + Google Meet"}
          </button>
        </div>
      )}

      <div className="space-y-2 max-h-72 overflow-y-auto">
        {events.length === 0 && !loading && (
          <p className="text-xs text-slate-500">No events in the next 7 days.</p>
        )}
        {events.map((evt) => (
          <div
            key={evt.id}
            className={`rounded-lg border p-2.5 ${
              isToday(evt.start)
                ? "border-[var(--accent)]/30 bg-[var(--accent)]/[0.06]"
                : "border-white/[0.07] bg-black/20"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-xs font-semibold text-slate-100 truncate">{evt.title}</p>
              {isToday(evt.start) && (
                <span className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-[var(--accent)]/20 text-[var(--accent-text)]">
                  Today
                </span>
              )}
            </div>
            <p className="text-[10px] text-slate-400 mt-0.5 flex items-center gap-1">
              <Clock size={9} />
              {evt.all_day ? "All day" : formatEventTime(evt.start)}
            </p>
            {evt.attendees.length > 0 && (
              <p className="text-[10px] text-slate-500 mt-0.5 flex items-center gap-1 truncate">
                <Users size={9} />
                {evt.attendees.slice(0, 3).join(", ")}
                {evt.attendees.length > 3 && ` +${evt.attendees.length - 3}`}
              </p>
            )}
            {evt.meet_link && (
              <a
                href={evt.meet_link}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-block text-[10px] text-[var(--accent-text)] hover:underline"
              >
                Join Meet →
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
