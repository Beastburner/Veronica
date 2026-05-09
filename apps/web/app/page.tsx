"use client";

import { motion } from "framer-motion";
import { Activity, AlertTriangle, Bell, BrainCircuit, Code2, LayoutDashboard, Shield, TerminalSquare, X } from "lucide-react";
import React, { FormEvent, useCallback, useMemo, useRef, useState } from "react";
import { ArcCore } from "@/components/ArcCore";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { OperationsPanels } from "@/components/OperationsPanels";
// import VoicePanel from "@/components/VoicePanel"; // NOT IN USE — wake word listener disabled
import { VoiceInterface } from "@/components/VoiceInterface";
import { useMemoryEfficientState } from "@/hooks/useMemoryEfficientState";
import { useMounted } from "@/hooks/useMounted";
import { useTelemetry } from "@/hooks/useTelemetry";

function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let inCode = false;
  let codeBuf: string[] = [];
  let codeLang = "";

  const renderInline = (line: string, key: string | number) => {
    const parts: React.ReactNode[] = [];
    const re = /(\*\*(.+?)\*\*|`([^`]+)`|\*(.+?)\*)/g;
    let last = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(line)) !== null) {
      if (m.index > last) parts.push(line.slice(last, m.index));
      if (m[2]) parts.push(<strong key={`${key}-b${m.index}`} className="font-semibold text-white">{m[2]}</strong>);
      else if (m[3]) parts.push(<code key={`${key}-c${m.index}`} className="rounded bg-black/40 px-1 py-0.5 font-mono text-[11px] text-cyan-300">{m[3]}</code>);
      else if (m[4]) parts.push(<em key={`${key}-i${m.index}`} className="italic text-slate-300">{m[4]}</em>);
      last = m.index + m[0].length;
    }
    if (last < line.length) parts.push(line.slice(last));
    return parts;
  };

  lines.forEach((line, i) => {
    if (line.startsWith("```")) {
      if (!inCode) {
        inCode = true;
        codeLang = line.slice(3).trim();
        codeBuf = [];
      } else {
        nodes.push(
          <pre key={`code-${i}`} className="my-2 overflow-x-auto rounded-lg border border-white/10 bg-black/50 p-3 font-mono text-[11px] leading-relaxed text-emerald-300">
            <code>{codeBuf.join("\n")}</code>
          </pre>
        );
        inCode = false;
        codeLang = "";
        codeBuf = [];
      }
      return;
    }
    if (inCode) { codeBuf.push(line); return; }

    if (/^#{1,3} /.test(line)) {
      const level = line.match(/^(#+) /)?.[1].length ?? 1;
      const content = line.replace(/^#+\s/, "");
      const cls = level === 1 ? "text-base font-bold text-white mt-2 mb-1" : "text-sm font-semibold text-slate-100 mt-1.5 mb-0.5";
      nodes.push(<p key={i} className={cls}>{renderInline(content, i)}</p>);
      return;
    }
    if (/^[-*] /.test(line)) {
      nodes.push(
        <div key={i} className="flex items-start gap-2 my-0.5">
          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: "var(--accent-strong)" }} />
          <span className="leading-relaxed">{renderInline(line.slice(2), i)}</span>
        </div>
      );
      return;
    }
    if (/^\d+\. /.test(line)) {
      const num = line.match(/^(\d+)\. /)?.[1];
      nodes.push(
        <div key={i} className="flex items-start gap-2 my-0.5">
          <span className="mt-0.5 shrink-0 text-[10px] font-mono" style={{ color: "var(--accent-text)" }}>{num}.</span>
          <span className="leading-relaxed">{renderInline(line.replace(/^\d+\. /, ""), i)}</span>
        </div>
      );
      return;
    }
    if (line.trim() === "") {
      nodes.push(<div key={i} className="my-1" />);
      return;
    }
    nodes.push(<p key={i} className="leading-relaxed">{renderInline(line, i)}</p>);
  });

  if (inCode && codeBuf.length) {
    nodes.push(
      <pre key="code-tail" className="my-2 overflow-x-auto rounded-lg border border-white/10 bg-black/50 p-3 font-mono text-[11px] leading-relaxed text-emerald-300">
        <code>{codeBuf.join("\n")}</code>
      </pre>
    );
  }

  return nodes;
}

function fade(delayMs: number = 0) {
  if (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ) {
    return {};
  }
  return {
    initial: { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: { delay: delayMs / 1000, duration: 0.4, ease: "easeOut" },
  };
}

type Mode = "JARVIS" | "FRIDAY" | "VERONICA" | "SENTINEL";

type Message = {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const modes: Array<{ id: Mode; label: string; detail: string }> = [
  { id: "JARVIS",   label: "JARVIS",   detail: "General intelligence" },
  { id: "FRIDAY",   label: "FRIDAY",   detail: "Productivity control" },
  { id: "VERONICA", label: "VERONICA", detail: "Problem response" },
  { id: "SENTINEL", label: "SENTINEL", detail: "Security watch" },
];

const starterTasks = [
  "Deploy coding mode",
  "Analyze this architecture",
  "Run optimization simulation",
  "What should I focus on today?",
];

export default function Home() {
  const mounted = useMounted();
  const [mode, setMode] = useState<Mode>("JARVIS");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [chatLatency, setChatLatency] = useState<number | null>(null);
  const sessionId = useRef<string>(
    (() => {
      if (typeof window !== "undefined") {
        const stored = window.localStorage.getItem("veronica-session-id");
        if (stored) return stored;
      }
      const newId =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `veronica-${Date.now()}`;
      if (typeof window !== "undefined") {
        window.localStorage.setItem("veronica-session-id", newId);
      }
      return newId;
    })()
  );

  const { items: messages, add: addMessage, replace: replaceMessages } = useMemoryEfficientState<Message>(
    [
      {
        role: "assistant",
        content:
          "Sir, VERONICA is online. Command center initialized, modes armed, voice pipeline standing by. Subtle, tasteful, mildly overqualified.",
      },
    ],
    100
  );
  const [notifications, setNotifications] = useState([
    "Action logging active",
    "Dangerous commands require confirmation",
    "Long-term memory online",
  ]);

  const telemetry = useTelemetry(10_000);

  const activeBriefing = useMemo(() => {
    if (mode === "FRIDAY")   return "Productivity routing active. Calendar, reminders, planning, drafting are prioritized.";
    if (mode === "VERONICA") return "Emergency reasoning active. Simulation, risk ranking, decisive recommendations are prioritized.";
    if (mode === "SENTINEL") return "Security monitoring active. Permissions, secrets, suspicious actions are under review.";
    return "General intelligence active. Context, tools, concise technical guidance are prioritized.";
  }, [mode]);

  const latestAssistantReply = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (m?.role === "assistant" && !m.streaming) return m.content;
    }
    return "";
  }, [messages]);

  const sendMessage = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed || busy) return;

      setBusy(true);
      setInput("");
      addMessage({ role: "user", content: trimmed });

      const start = performance.now();
      try {
        const response = await fetch(`${API_URL}/chat/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Session-ID": sessionId.current,
          },
          body: JSON.stringify({
            message: trimmed,
            mode,
            history: messages.slice(-8).map(({ role, content }) => ({ role, content })),
            developer_mode: trimmed.toLowerCase().includes("code"),
          }),
        });

        if (!response.ok || !response.body) throw new Error("Backend offline");

        addMessage({ role: "assistant", content: "", streaming: true });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let assembled = "";

        const drain = (events: string[]) => {
          for (const evt of events) {
            const line = evt.trim();
            if (!line.startsWith("data:")) continue;
            const json = line.slice(5).trim();
            if (!json) continue;
            try {
              const parsed = JSON.parse(json);
              if (parsed.type === "token" && typeof parsed.content === "string") {
                assembled += parsed.content;
                replaceMessages([
                  ...messages,
                  { role: "user", content: trimmed },
                  { role: "assistant", content: assembled, streaming: true },
                ]);
              } else if (parsed.type === "done") {
                if (parsed.protocol) {
                  setNotifications((n) => [`Protocol engaged: ${parsed.protocol}`, ...n].slice(0, 5));
                }
                if (
                  parsed.provider_status &&
                  parsed.provider_status !== "ok" &&
                  !String(parsed.provider_status).startsWith("direct")
                ) {
                  setNotifications((n) => [`Model status: ${parsed.provider_status}`, ...n].slice(0, 5));
                }
              }
            } catch {
              /* skip malformed SSE lines */
            }
          }
        };

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";
          drain(parts);
        }
        if (buffer.trim()) drain([buffer]);

        replaceMessages([
          ...messages,
          { role: "user", content: trimmed },
          { role: "assistant", content: assembled || "..." },
        ]);
        setChatLatency(Math.round(performance.now() - start));
      } catch {
        addMessage({
          role: "assistant",
          content:
            "Sir, the backend is not responding. Frontend remains operational; bring the FastAPI service up on port 8000.",
        });
      } finally {
        setBusy(false);
      }
    },
    [addMessage, busy, messages, mode, replaceMessages]
  );

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMessage(input);
  }

  const modeKey = mode.toLowerCase();
  const apiOffline    = !telemetry.online;
  const modelOffline  = telemetry.online && telemetry.model != null && !telemetry.model.configured;
  const noKeySet      = modelOffline && telemetry.model != null && !telemetry.model.provider_key_present;
  const allRateLimited = modelOffline && telemetry.model != null && telemetry.model.provider_key_present;

  const [showLeft, setShowLeft] = useState(false);
  const [showRight, setShowRight] = useState(false);

  return (
    <main
      data-mode={modeKey}
      className="relative min-h-screen overflow-x-hidden px-3 py-3 text-slate-100 sm:px-4 sm:py-4"
    >
      <div className="scanlines absolute inset-0 opacity-25" />

      {/* Status banners */}
      {apiOffline && (
        <div className="relative z-20 mx-auto mb-3 max-w-7xl flex flex-wrap items-center gap-2 rounded-lg border border-red-500/50 bg-red-900/40 px-3 py-2 text-xs text-red-200 sm:text-sm sm:px-4">
          <AlertTriangle size={14} className="shrink-0" />
          API OFFLINE — <code className="font-mono text-xs">uvicorn app.main:app --reload</code>
        </div>
      )}
      {noKeySet && (
        <div className="relative z-20 mx-auto mb-3 max-w-7xl flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-900/30 px-3 py-2 text-xs text-amber-200 sm:text-sm sm:px-4">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>Ollama not reachable — run <code className="font-mono text-xs text-amber-100">ollama serve</code> then <code className="font-mono text-xs text-amber-100">ollama pull qwen2.5:7b</code></span>
        </div>
      )}
      {allRateLimited && (
        <div className="relative z-20 mx-auto mb-3 max-w-7xl flex items-center gap-2 rounded-lg border border-orange-500/40 bg-orange-900/30 px-3 py-2 text-xs text-orange-200 sm:text-sm sm:px-4">
          <AlertTriangle size={14} className="shrink-0" />
          Ollama unreachable — check <code className="font-mono text-xs ml-1">ollama serve</code>
        </div>
      )}

      {/* Mobile top bar */}
      <div className="mobile-topbar relative z-20 mb-3 items-center justify-between">
        <button
          onClick={() => { setShowLeft(true); setShowRight(false); }}
          className="flex items-center gap-2 rounded-lg border border-[var(--accent)]/30 bg-black/40 px-3 py-2 text-xs text-[var(--accent-text)] backdrop-blur"
        >
          <BrainCircuit size={14} /> Command OS
        </button>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold tracking-widest" style={{ color: "var(--accent-text)" }}>{mode}</span>
        </div>
        <button
          onClick={() => { setShowRight(true); setShowLeft(false); }}
          className="flex items-center gap-2 rounded-lg border border-[var(--accent)]/30 bg-black/40 px-3 py-2 text-xs text-[var(--accent-text)] backdrop-blur"
        >
          <LayoutDashboard size={14} /> Tools
        </button>
      </div>

      {/* Mobile left panel drawer */}
      {showLeft && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowLeft(false)} />
          <motion.div
            initial={{ x: -320 }} animate={{ x: 0 }} transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="relative z-10 h-full w-[300px] max-w-[85vw] overflow-y-auto bg-[#04060a] border-r border-[var(--accent)]/20 p-4"
          >
            <button onClick={() => setShowLeft(false)} className="absolute right-3 top-3 rounded-lg border border-white/10 p-1.5 text-slate-400 hover:text-white">
              <X size={14} />
            </button>
            <LeftPanelContent mode={mode} setMode={setMode} apiOffline={apiOffline} telemetry={telemetry} chatLatency={chatLatency} mounted={mounted} />
          </motion.div>
        </div>
      )}

      {/* Mobile right panel drawer */}
      {showRight && (
        <div className="fixed inset-0 z-50 flex justify-end lg:hidden">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowRight(false)} />
          <motion.div
            initial={{ x: 320 }} animate={{ x: 0 }} transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="relative z-10 h-full w-[300px] max-w-[85vw] overflow-y-auto bg-[#04060a] border-l border-[var(--accent)]/20 p-4"
          >
            <button onClick={() => setShowRight(false)} className="absolute left-3 top-3 rounded-lg border border-white/10 p-1.5 text-slate-400 hover:text-white">
              <X size={14} />
            </button>
            <RightPanelContent
              starterTasks={starterTasks}
              notifications={notifications}
              busy={busy}
              sendMessage={sendMessage}
              mounted={mounted}
            />
          </motion.div>
        </div>
      )}

      <div className="app-grid relative z-10 mx-auto max-w-7xl">

        {/* ── LEFT PANEL — desktop only ──────────────── */}
        <motion.aside
          {...(mounted ? fade(0) : {})}
          className="panel-left hud-panel rounded-lg p-4"
        >
          <LeftPanelContent mode={mode} setMode={setMode} apiOffline={apiOffline} telemetry={telemetry} chatLatency={chatLatency} mounted={mounted} />
        </motion.aside>

        {/* ── CENTER ────────────────────────────────── */}
        <section className="app-grid-center grid gap-4">
          <motion.div
            {...(mounted ? fade(150) : {})}
            className="hud-panel rounded-lg p-3 sm:p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs uppercase tracking-[0.2em]" style={{ color: "var(--accent-text)" }}>
                  Active Mode: {mode}
                </p>
                <h2 className="mt-1 text-xl font-semibold sm:text-2xl lg:text-3xl truncate">Arc command interface</h2>
              </div>
              <div className="rounded-lg border border-[var(--accent)]/30 bg-black/30 px-2 py-1.5 text-sm sm:px-3 sm:py-2">
                <VoiceInterface
                  onCommand={(text) => void sendMessage(text)}
                  speak={latestAssistantReply}
                  busy={busy}
                  onRecordingChange={setIsRecording}
                />
              </div>
            </div>
            <ErrorBoundary name="ArcCore">
              <ArcCore mode={mode} isThinking={busy} isListening={isRecording} />
            </ErrorBoundary>
            <p className="mx-auto max-w-2xl text-center text-xs text-slate-300 sm:text-sm">{activeBriefing}</p>
          </motion.div>

          <motion.div
            {...(mounted ? fade(210) : {})}
            className="hud-panel rounded-lg p-3 sm:p-4"
          >
            <div className="mb-3 flex items-center justify-between">
              <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
                <TerminalSquare size={16} /> Conversational AI
              </p>
              <span className="text-xs text-slate-400">{busy ? "Thinking…" : "Ready"}</span>
            </div>

            <div className="chat-scroll space-y-3 overflow-y-auto pr-1">
              {messages.map((message, index) => (
                <div
                  key={`${message.role}-${index}`}
                  className={`rounded-lg border p-3 text-sm leading-6 ${
                    message.role === "assistant"
                      ? "border-[var(--accent)]/20 bg-[var(--accent)]/[0.06] text-[var(--accent-text)]"
                      : "ml-auto max-w-[90%] border-pink-300/20 bg-pink-400/[0.07] text-pink-50"
                  }`}
                >
                  <p className="mb-1 text-xs uppercase tracking-[0.18em] text-slate-400">
                    {message.role === "assistant" ? "VERONICA" : "COMMANDER"}
                  </p>
                  <div className="space-y-0.5 text-sm break-words min-w-0">{renderMarkdown(message.content)}</div>
                  {message.streaming && index === messages.length - 1 ? (
                    <span
                      className="inline-block w-0.5 h-4 ml-0.5 align-middle animate-pulse"
                      style={{ background: "var(--accent-strong)" }}
                    />
                  ) : null}
                </div>
              ))}
            </div>

            <form onSubmit={onSubmit} className="mt-3 flex gap-2">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Veronica, deploy coding mode."
                className="min-w-0 flex-1 rounded-lg border border-[var(--accent)]/20 bg-black/30 px-3 py-2.5 text-sm text-white outline-none transition placeholder:text-slate-400 focus:border-[var(--accent-strong)] sm:py-3"
              />
              <button
                disabled={busy}
                className="rounded-lg border border-[var(--accent)]/40 bg-[var(--accent)]/15 px-4 py-2.5 text-sm font-semibold text-[var(--accent-text)] transition hover:bg-[var(--accent)]/25 disabled:cursor-not-allowed disabled:opacity-50 sm:px-5 sm:py-3"
              >
                Send
              </button>
            </form>
          </motion.div>

          <motion.div {...(mounted ? fade(270) : {})}>
            <ErrorBoundary name="OperationsPanels">
              <OperationsPanels />
            </ErrorBoundary>
          </motion.div>
        </section>

        {/* ── RIGHT PANEL — desktop only ─────────────── */}
        <aside className="panel-right min-w-0 overflow-hidden space-y-4">
          <RightPanelContent
            starterTasks={starterTasks}
            notifications={notifications}
            busy={busy}
            sendMessage={sendMessage}
            mounted={mounted}
          />
        </aside>
      </div>
    </main>
  );
}

function Row({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="flex items-center justify-between gap-2" title={title}>
      <span className="text-slate-400">{label}</span>
      <span className="truncate text-right text-slate-200" style={{ maxWidth: "60%" }}>
        {value}
      </span>
    </div>
  );
}

type SysStats = { cpu_percent: number; ram_percent: number; ram_used_gb: number; ram_total_gb: number; disk_percent: number; disk_used_gb: number; disk_total_gb: number } | null;

function SystemMonitor({
  apiOffline, model, system, latencyMs, chatLatency, mounted,
}: {
  apiOffline: boolean;
  model: Record<string, unknown> | null | undefined;
  system: Record<string, unknown> | null | undefined;
  latencyMs: number | null | undefined;
  chatLatency: number | null;
  mounted: boolean;
}) {
  const [stats, setStats] = React.useState<SysStats>(null);
  const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  React.useEffect(() => {
    if (apiOffline) return;
    const load = () => fetch(`${API}/system/stats`).then((r) => r.ok ? r.json() : null).then((d) => { if (d) setStats(d); }).catch(() => null);
    load();
    const iv = setInterval(load, 10000);
    return () => clearInterval(iv);
  }, [apiOffline]);

  const bar = (pct: number) => (
    <div className="h-1 rounded-full bg-white/10 overflow-hidden">
      <div className="h-full rounded-full" style={{ width: `${Math.min(pct, 100)}%`, background: pct > 85 ? "#f87171" : pct > 60 ? "#fb923c" : "var(--accent-strong)" }} />
    </div>
  );

  const m = model as Record<string, unknown> | null | undefined;

  return (
    <motion.div {...(mounted ? fade(60) : {})} className="mt-5 rounded-lg border border-white/10 bg-black/20 p-3">
      <div className="mb-3 flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <Activity size={16} /> System Monitor
        </p>
        <span className={`rounded px-2 py-0.5 text-[10px] font-semibold tracking-[0.18em] ${apiOffline ? "bg-pink-500/20 text-pink-200" : "bg-emerald-500/15 text-emerald-200"}`}>
          {apiOffline ? "OFFLINE" : "ONLINE"}
        </span>
      </div>
      <div className="space-y-2 text-xs">
        <Row label="Model" value={m?.model ? String(m.model) : "--"} />
        <Row label="Ollama" value={!m ? "--" : m.running ? "running ✓" : "unreachable"} />
        {stats && (
          <>
            <div>
              <div className="flex justify-between mb-0.5"><span className="text-slate-400">CPU</span><span className="text-slate-200">{stats.cpu_percent.toFixed(0)}%</span></div>
              {bar(stats.cpu_percent)}
            </div>
            <div>
              <div className="flex justify-between mb-0.5"><span className="text-slate-400">RAM</span><span className="text-slate-200">{stats.ram_used_gb}/{stats.ram_total_gb} GB</span></div>
              {bar(stats.ram_percent)}
            </div>
            <div>
              <div className="flex justify-between mb-0.5"><span className="text-slate-400">Disk</span><span className="text-slate-200">{stats.disk_used_gb}/{stats.disk_total_gb} GB</span></div>
              {bar(stats.disk_percent)}
            </div>
          </>
        )}
        <Row label="Sessions" value={system?.active_sessions != null ? String(system.active_sessions) : "--"} />
        <Row label="Latency" value={latencyMs != null ? `${latencyMs} ms` : "--"} />
        <Row label="Last reply" value={chatLatency != null ? `${chatLatency} ms` : "--"} />
      </div>
    </motion.div>
  );
}

function PomodoroWidget({ onSend }: { onSend: (msg: string) => void }) {
  const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const [status, setStatus] = React.useState<{ active: boolean; label: string; elapsed_seconds: number; remaining_seconds: number; percent_done: number } | null>(null);
  const [labelInput, setLabelInput] = React.useState("");

  React.useEffect(() => {
    const load = () => fetch(`${API}/pomodoro/status`).then((r) => r.ok ? r.json() : null).then((d) => { if (d) setStatus(d); }).catch(() => null);
    load();
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, []);

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  const start = async () => {
    const label = labelInput.trim() || "Focus session";
    await fetch(`${API}/pomodoro/start`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ label, duration_minutes: 25 }) });
    setLabelInput("");
    setTimeout(() => fetch(`${API}/pomodoro/status`).then((r) => r.json()).then(setStatus).catch(() => null), 300);
  };

  const stop = async () => {
    await fetch(`${API}/pomodoro/stop`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ completed: false }) });
    setStatus(null);
  };

  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-3">
      <p className="mb-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>⏱ Focus Timer</p>
      {status?.active ? (
        <>
          <p className="text-xs text-slate-400 mb-1 truncate">{status.label}</p>
          <div className="h-1 rounded-full bg-white/10 overflow-hidden mb-2">
            <div className="h-full rounded-full transition-all" style={{ width: `${status.percent_done}%`, background: "var(--accent-strong)" }} />
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-200 font-mono">{fmt(status.remaining_seconds)} left</span>
            <button onClick={() => void stop()} className="text-pink-300 hover:text-pink-100 transition">Stop</button>
          </div>
        </>
      ) : (
        <div className="flex gap-2">
          <input value={labelInput} onChange={(e) => setLabelInput(e.target.value)} placeholder="Task label (optional)"
            className="min-w-0 flex-1 rounded border border-white/10 bg-black/30 px-2 py-1 text-xs text-white outline-none placeholder:text-slate-500" />
          <button onClick={() => void start()} className="rounded border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-2 py-1 text-xs text-[var(--accent-text)] hover:bg-[var(--accent)]/20 transition">
            25 min
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Extracted panel content components ──────────────────── */

function LeftPanelContent({
  mode, setMode, apiOffline, telemetry, chatLatency, mounted,
}: {
  mode: Mode;
  setMode: (m: Mode) => void;
  apiOffline: boolean;
  telemetry: { model: Record<string, unknown> | null | undefined; system: Record<string, unknown> | null | undefined; latencyMs: number | null | undefined; online: boolean };
  chatLatency: number | null;
  mounted: boolean;
}) {
  return (
    <>
      <div className="flex items-center gap-3 border-b border-[var(--accent)]/20 pb-4">
        <BrainCircuit style={{ color: "var(--accent-strong)" }} />
        <div>
          <p className="text-xs uppercase tracking-[0.28em]" style={{ color: "var(--accent-text)" }}>VERONICA</p>
          <h1 className="text-xl font-semibold">Command OS</h1>
        </div>
      </div>

      <div className="mt-5 space-y-2">
        {modes.map((item) => {
          const active = mode === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setMode(item.id)}
              aria-pressed={active}
              className={`w-full rounded-lg border p-3 text-left transition ${
                active
                  ? "border-[var(--accent-strong)] bg-[var(--accent)]/12 text-white shadow-hud"
                  : "border-white/10 bg-white/[0.03] text-slate-300 hover:border-[var(--accent)]/50"
              }`}
            >
              <span className="block text-sm font-semibold">{item.label}</span>
              <span className="text-xs text-slate-400">{item.detail}</span>
            </button>
          );
        })}
      </div>

      {mode === "SENTINEL" && (
        <div
          className="mt-3 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs"
          style={{ color: "var(--accent-strong)", borderColor: "var(--accent-border)", background: "var(--accent-glow)" }}
        >
          <span className="animate-pulse">&#9679;</span>
          <span className="uppercase tracking-widest">THREAT LEVEL: MONITORING</span>
        </div>
      )}

      <SystemMonitor
        apiOffline={apiOffline}
        model={telemetry.model}
        system={telemetry.system}
        latencyMs={telemetry.latencyMs}
        chatLatency={chatLatency}
        mounted={mounted}
      />
    </>
  );
}

function RightPanelContent({
  starterTasks, notifications, busy, sendMessage, mounted,
}: {
  starterTasks: string[];
  notifications: string[];
  busy: boolean;
  sendMessage: (msg: string) => void;
  mounted: boolean;
}) {
  return (
    <>
      <motion.div {...(mounted ? fade(300) : {})} className="hud-panel min-w-0 overflow-hidden rounded-lg p-4">
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <Code2 size={16} /> Protocols
        </p>
        <div className="space-y-2">
          {starterTasks.map((task) => (
            <button
              key={task}
              onClick={() => void sendMessage(`Veronica, ${task.toLowerCase()}.`)}
              className="w-full rounded-lg border border-white/10 bg-white/[0.03] p-3 text-left text-sm text-slate-200 transition hover:border-[var(--accent)]/40 hover:bg-[var(--accent)]/[0.07] break-words"
            >
              {task}
            </button>
          ))}
        </div>
      </motion.div>

      <motion.div {...(mounted ? fade(360) : {})} className="hud-panel min-w-0 overflow-hidden rounded-lg p-4">
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <Shield size={16} /> Security Rules
        </p>
        <div className="space-y-3 text-sm text-slate-300">
          <p>Dangerous actions require confirmation.</p>
          <p>Secrets stay server-side.</p>
          <p>Autonomous steps are logged.</p>
          <p>Shell execution is whitelist-first.</p>
        </div>
      </motion.div>

      <motion.div {...(mounted ? fade(420) : {})} className="hud-panel min-w-0 overflow-hidden rounded-lg p-4">
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <Bell size={16} /> Live Notifications
        </p>
        <div className="space-y-2">
          {notifications.map((notification, index) => (
            <div key={`${notification}-${index}`} className="rounded-lg border border-white/10 bg-black/20 p-3 text-xs text-slate-300 break-words">
              {notification}
            </div>
          ))}
        </div>
      </motion.div>
    </>
  );
}
