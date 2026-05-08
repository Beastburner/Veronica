"use client";

import { useEffect, useState } from "react";
import { MessageCircle, RefreshCw } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type WAStatus = { ready: boolean; has_qr: boolean; initializing?: boolean; ok?: boolean; error?: string };
type WAQR = { ready: boolean; qr: string | null };
type WAMessage = {
  id: string;
  from: string;
  fromName: string;
  to: string | null;
  toName: string | null;
  body: string;
  timestamp: number;
  isGroup: boolean;
  fromMe: boolean;
};
type WAMessages = { messages: WAMessage[]; total: number };

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// Group messages by the other party (contact name for received, toName for sent)
function groupByContact(msgs: WAMessage[]): Map<string, WAMessage[]> {
  const map = new Map<string, WAMessage[]>();
  for (const m of msgs) {
    const key = m.fromMe
      ? (m.toName || m.to || "Sent")
      : (m.fromName || m.from);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(m);
  }
  return map;
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  if (isToday) return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function WhatsAppPanel() {
  const [status, setStatus] = useState<WAStatus | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [messages, setMessages] = useState<WAMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [starting, setStarting] = useState(false);

  const btn =
    "rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-3 py-1.5 text-xs text-[var(--accent-text)] hover:bg-[var(--accent)]/20 transition disabled:opacity-50";

  async function loadStatus() {
    try {
      const s = await apiFetch<WAStatus>("/whatsapp/status");

      // Backend returns {ok: false, error: "..."} when Node service is unreachable
      if (s.ok === false || (!s.ready && !s.has_qr && s.error)) {
        setError("WhatsApp service offline. Run: cd apps/whatsapp && node index.js");
        setStatus(null);
        setLoading(false);
        return;
      }

      setStatus(s);
      if (s.has_qr) {
        const qrData = await apiFetch<WAQR>("/whatsapp/qr");
        setQr(qrData.qr);
      } else if (s.ready) {
        setQr(null);
        const data = await apiFetch<WAMessages>("/whatsapp/messages?limit=100");
        setMessages(data.messages ?? []);
      } else {
        setQr(null);
      }
      setError(null);
    } catch {
      setError("WhatsApp service offline. Run: cd apps/whatsapp && node index.js");
    } finally {
      setLoading(false);
    }
  }

  async function handleRefresh() {
    setRefreshing(true);
    setError(null);
    setLoading(true);
    await loadStatus();
    setRefreshing(false);
  }

  const [resetting, setResetting] = useState(false);

  async function handleStart() {
    setStarting(true);
    setError(null);
    try {
      await fetch(`${API_URL}/whatsapp/start`, { method: "POST" });
      for (let i = 0; i < 5; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const s = await apiFetch<WAStatus>("/whatsapp/status").catch(() => null);
        if (s && s.ok !== false && (s.ready || s.has_qr)) {
          await loadStatus();
          break;
        }
      }
    } catch {
      setError("Could not contact backend.");
    } finally {
      setStarting(false);
      await loadStatus();
    }
  }

  async function handleReset() {
    setResetting(true);
    setError(null);
    try {
      await fetch(`${API_URL}/whatsapp/reset`, { method: "POST" });
      // wait for QR to appear
      for (let i = 0; i < 10; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const s = await apiFetch<WAStatus>("/whatsapp/status").catch(() => null);
        if (s && (s.ready || s.has_qr)) {
          await loadStatus();
          break;
        }
      }
    } catch {
      setError("Could not contact backend.");
    } finally {
      setResetting(false);
      await loadStatus();
    }
  }

  useEffect(() => {
    void loadStatus();
    const iv = setInterval(() => void loadStatus(), 15000);
    return () => clearInterval(iv);
  }, []);

  const grouped = groupByContact(messages);

  return (
    <div className="hud-panel rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <MessageCircle size={16} /> WhatsApp
        </p>
        <button onClick={() => void handleRefresh()} disabled={refreshing || loading} className={btn} title="Refresh">
          <RefreshCw size={12} className={`inline mr-1 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {loading && <p className="text-sm text-slate-400">Connecting…</p>}

      {!loading && !error && status && !status.ready && !status.has_qr && status.initializing && (
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
          <span className="text-xs text-amber-300">Starting WhatsApp (launching browser…)</span>
        </div>
      )}

      {!loading && !error && status && !status.ready && !status.has_qr && !status.initializing && (
        <div className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 px-3 py-3">
          <span className="text-xs text-slate-400">Session may be stale — reset to get a new QR</span>
          <button
            onClick={() => void handleReset()}
            disabled={resetting}
            className={`${btn} text-[10px] px-2 py-1`}
          >
            {resetting ? "Resetting…" : "Reset QR"}
          </button>
        </div>
      )}

      {!loading && error && (
        <div className="space-y-3 rounded-lg border border-white/10 bg-black/20 px-3 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-slate-500" />
              <span className="text-xs text-slate-400">Service offline</span>
            </div>
            <button
              onClick={() => void handleStart()}
              disabled={starting}
              className={`${btn} text-[10px] px-2 py-1`}
            >
              {starting ? "Starting…" : "Start"}
            </button>
          </div>
          <p className="text-[10px] text-slate-600 font-mono">cd apps/whatsapp &amp;&amp; npm install (first time)</p>
        </div>
      )}

      {!loading && !error && status && !status.ready && status.has_qr && qr && (
        <div className="space-y-3">
          <p className="text-sm text-slate-300">Scan this QR code with WhatsApp on your phone:</p>
          <div className="flex justify-center">
            <img
              src={qr}
              alt="WhatsApp QR code"
              className="rounded-lg border border-white/10 bg-white p-2"
              style={{ maxWidth: 240 }}
            />
          </div>
          <p className="text-xs text-slate-400 text-center">QR updates automatically every 15 seconds</p>
        </div>
      )}

      {!loading && !error && status?.ready && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span className="text-xs text-emerald-300">Connected</span>
            <span className="ml-auto text-xs text-slate-500">{messages.length} messages</span>
          </div>

          {messages.length === 0 ? (
            <p className="text-sm text-slate-400">No messages yet.</p>
          ) : (
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {Array.from(grouped.entries()).map(([contact, msgs]) => (
                <div key={contact} className="rounded-lg border border-white/10 bg-black/20 p-3 space-y-2">
                  <p className="text-xs font-semibold text-[var(--accent-text)] truncate">
                    {contact}
                    {msgs[0].isGroup && (
                      <span className="ml-2 text-slate-500 font-normal">[group]</span>
                    )}
                  </p>
                  <div className="space-y-1.5">
                    {msgs.slice(0, 5).map((m) => (
                      <div
                        key={m.id}
                        className={`flex items-start gap-2 ${m.fromMe ? "flex-row-reverse" : ""}`}
                      >
                        {m.fromMe && (
                          <span className="text-[10px] text-slate-500 flex-shrink-0 mt-0.5">You</span>
                        )}
                        <p className={`text-sm truncate flex-1 ${m.fromMe ? "text-right text-slate-400" : "text-slate-300"}`}>
                          {m.body}
                        </p>
                        <span className="text-xs text-slate-500 flex-shrink-0">{formatTime(m.timestamp)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
