"use client";

import { Mail, RefreshCw, Send, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function decodeHtml(s: string): string {
  return s
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ");
}

function cleanFrom(from: string): string {
  const name = from.split("<")[0].trim().replace(/^["']+|["']+$/g, "");
  return name || from;
}

type EmailItem = {
  id: string;
  from: string;
  subject: string;
  date: string;
  snippet: string;
  unread?: boolean;
};

type OAuthStatus = { google_configured: boolean; gmail: boolean };

type ComposeState = { to: string; subject: string; body: string };

export function EmailPanel() {
  const [status, setStatus] = useState<OAuthStatus | null>(null);
  const [emails, setEmails] = useState<EmailItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedBody, setSelectedBody] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);
  const [compose, setCompose] = useState<ComposeState>({ to: "", subject: "", body: "" });
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQ, setSearchQ] = useState("");

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/oauth/status`);
      const data = await res.json();
      setStatus(data as OAuthStatus);
    } catch {
      setStatus({ google_configured: false, gmail: false });
    }
  }, []);

  const fetchInbox = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/email/inbox?max_results=15`);
      const data = await res.json();
      if (data.ok) {
        setEmails(data.result as EmailItem[]);
      } else {
        setError(data.error ?? "Failed to load inbox");
      }
    } catch {
      setError("Cannot reach API");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (status?.gmail) void fetchInbox();
  }, [status, fetchInbox]);

  // Check for ?connected=google after OAuth redirect
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected") === "google") {
      window.history.replaceState({}, "", window.location.pathname);
      void fetchStatus();
    }
  }, [fetchStatus]);

  async function openEmail(id: string) {
    setSelected(id);
    setSelectedBody(null);
    try {
      const res = await fetch(`${API}/email/message/${id}`);
      const data = await res.json();
      if (data.ok) setSelectedBody(data.result.body);
    } catch {
      setSelectedBody("Failed to load email body.");
    }
  }

  async function handleSend() {
    if (!compose.to || !compose.subject) return;
    setSending(true);
    try {
      const res = await fetch(`${API}/email/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(compose),
      });
      const data = await res.json();
      if (data.ok) {
        setComposing(false);
        setCompose({ to: "", subject: "", body: "" });
      } else {
        setError(data.error ?? "Failed to send");
      }
    } catch {
      setError("Send failed");
    } finally {
      setSending(false);
    }
  }

  async function handleSearch() {
    if (!searchQ.trim()) return void fetchInbox();
    setLoading(true);
    try {
      const res = await fetch(`${API}/email/search?q=${encodeURIComponent(searchQ)}`);
      const data = await res.json();
      if (data.ok) setEmails(data.result as EmailItem[]);
    } catch {
      setError("Search failed");
    } finally {
      setLoading(false);
    }
  }

  if (!status) {
    return (
      <div className="hud-panel rounded-lg p-4 text-sm text-slate-400">
        <p className="flex items-center gap-2 font-semibold" style={{ color: "var(--accent-text)" }}>
          <Mail size={16} /> Mail
        </p>
        <p className="mt-3">Loading...</p>
      </div>
    );
  }

  if (!status.google_configured) {
    return (
      <div className="hud-panel rounded-lg p-4">
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <Mail size={16} /> Mail
        </p>
        <p className="text-xs text-slate-400">
          Add <code className="text-cyan-300">GOOGLE_CLIENT_ID</code> and{" "}
          <code className="text-cyan-300">GOOGLE_CLIENT_SECRET</code> to{" "}
          <code className="text-cyan-300">apps/api/.env</code> to enable Gmail.
        </p>
      </div>
    );
  }

  if (!status.gmail) {
    return (
      <div className="hud-panel rounded-lg p-4">
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <Mail size={16} /> Mail
        </p>
        <p className="mb-4 text-xs text-slate-400">Connect your Gmail account to read and send mail from VERONICA.</p>
        <a
          href={`${API}/oauth/google/start`}
          className="inline-block rounded-lg border border-[var(--accent)]/40 bg-[var(--accent)]/15 px-4 py-2 text-sm font-semibold text-[var(--accent-text)] hover:bg-[var(--accent)]/25 transition"
        >
          Connect Gmail
        </a>
      </div>
    );
  }

  return (
    <div className="hud-panel rounded-lg p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <Mail size={16} /> Mail
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => setComposing(true)}
            className="rounded border border-[var(--accent)]/30 px-3 py-1 text-xs text-[var(--accent-text)] hover:bg-[var(--accent)]/10 transition"
          >
            Compose
          </button>
          <button
            onClick={() => void fetchInbox()}
            disabled={loading}
            className="rounded border border-white/10 p-1 text-slate-400 hover:text-white transition disabled:opacity-40"
          >
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

      <div className="mb-3 flex gap-2">
        <input
          value={searchQ}
          onChange={(e) => setSearchQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void handleSearch()}
          placeholder="Search mail..."
          className="min-w-0 flex-1 rounded border border-white/10 bg-black/30 px-3 py-1.5 text-xs text-white outline-none placeholder:text-slate-500 focus:border-[var(--accent-strong)]"
        />
        <button onClick={() => void handleSearch()} className="rounded border border-white/10 px-3 py-1.5 text-xs text-slate-300 hover:text-white transition">
          Search
        </button>
      </div>

      {composing && (
        <div className="mb-3 rounded-lg border border-[var(--accent)]/30 bg-black/30 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[var(--accent-text)]">New Message</span>
            <button onClick={() => setComposing(false)}><X size={12} className="text-slate-400" /></button>
          </div>
          {(["to", "subject"] as const).map((field) => (
            <input
              key={field}
              placeholder={field === "to" ? "To" : "Subject"}
              value={compose[field]}
              onChange={(e) => setCompose((c) => ({ ...c, [field]: e.target.value }))}
              className="w-full rounded border border-white/10 bg-black/40 px-3 py-1.5 text-xs text-white outline-none placeholder:text-slate-500 focus:border-[var(--accent-strong)]"
            />
          ))}
          <textarea
            placeholder="Message body..."
            value={compose.body}
            onChange={(e) => setCompose((c) => ({ ...c, body: e.target.value }))}
            rows={4}
            className="w-full rounded border border-white/10 bg-black/40 px-3 py-1.5 text-xs text-white outline-none resize-none placeholder:text-slate-500 focus:border-[var(--accent-strong)]"
          />
          <button
            onClick={() => void handleSend()}
            disabled={sending || !compose.to || !compose.subject}
            className="flex items-center gap-2 rounded border border-[var(--accent)]/40 bg-[var(--accent)]/15 px-4 py-1.5 text-xs font-semibold text-[var(--accent-text)] disabled:opacity-40 hover:bg-[var(--accent)]/25 transition"
          >
            <Send size={12} /> {sending ? "Sending..." : "Send"}
          </button>
        </div>
      )}

      {selected && (
        <div className="mb-3 rounded-lg border border-white/10 bg-black/20 p-3 min-w-0 overflow-hidden">
          <div className="mb-2 flex items-start justify-between gap-2 min-w-0">
            <p className="text-xs font-semibold text-slate-200 truncate min-w-0">
              {decodeHtml(emails.find((e) => e.id === selected)?.subject ?? "Email")}
            </p>
            <button onClick={() => { setSelected(null); setSelectedBody(null); }}>
              <X size={12} className="text-slate-400 hover:text-white shrink-0" />
            </button>
          </div>
          <p className="text-xs text-slate-400 mb-2 truncate">{cleanFrom(emails.find((e) => e.id === selected)?.from ?? "")}</p>
          <pre className="text-xs text-slate-300 whitespace-pre-wrap break-words max-h-48 overflow-y-auto overflow-x-hidden">
            {selectedBody ?? "Loading..."}
          </pre>
          <button
            onClick={() => {
              const em = emails.find((e) => e.id === selected);
              if (em) {
                setComposing(true);
                setCompose({ to: em.from, subject: `Re: ${em.subject}`, body: "" });
              }
            }}
            className="mt-2 rounded border border-[var(--accent)]/30 px-3 py-1 text-xs text-[var(--accent-text)] hover:bg-[var(--accent)]/10 transition"
          >
            Reply
          </button>
        </div>
      )}

      <div className="space-y-1.5 max-h-64 overflow-y-auto">
        {emails.length === 0 && !loading && (
          <p className="text-xs text-slate-500">Inbox empty or no results.</p>
        )}
        {emails.map((email) => (
          <button
            key={email.id}
            onClick={() => void openEmail(email.id)}
            className={`w-full min-w-0 overflow-hidden rounded-lg border p-2.5 text-left transition ${
              selected === email.id
                ? "border-[var(--accent)]/40 bg-[var(--accent)]/10"
                : "border-white/[0.07] bg-black/20 hover:border-white/20"
            }`}
          >
            <div className="flex items-start justify-between gap-2 min-w-0">
              <p className={`text-xs font-semibold truncate min-w-0 ${email.unread ? "text-white" : "text-slate-300"}`}>
                {cleanFrom(email.from)}
              </p>
              <p className="text-[10px] text-slate-500 shrink-0">{email.date.split(",")[0]}</p>
            </div>
            <p className={`text-xs mt-0.5 truncate ${email.unread ? "text-slate-200" : "text-slate-400"}`}>
              {decodeHtml(email.subject)}
            </p>
            <p className="text-[10px] text-slate-500 mt-0.5 truncate">{decodeHtml(email.snippet)}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
