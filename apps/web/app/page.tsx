"use client";

import { motion } from "framer-motion";
import { Activity, Bell, BrainCircuit, Code2, Shield, TerminalSquare } from "lucide-react";
import { FormEvent, useCallback, useMemo, useRef, useState } from "react";
import { ArcCore } from "@/components/ArcCore";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { OperationsPanels } from "@/components/OperationsPanels";
import { VoiceInterface } from "@/components/VoiceInterface";
import { useMemoryEfficientState } from "@/hooks/useMemoryEfficientState";
import { useMounted } from "@/hooks/useMounted";
import { useTelemetry } from "@/hooks/useTelemetry";

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
    transition: { delay: delayMs / 1000, duration: 0.4 },
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
  { id: "JARVIS", label: "JARVIS", detail: "General intelligence" },
  { id: "FRIDAY", label: "FRIDAY", detail: "Productivity control" },
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
  const [chatLatency, setChatLatency] = useState<number | null>(null);
  const sessionId = useRef(
    typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `veronica-${Date.now()}`
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
    if (mode === "FRIDAY") return "Productivity routing active. Calendar, reminders, planning, drafting are prioritized.";
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
                if (parsed.provider_status && parsed.provider_status !== "ok" && !String(parsed.provider_status).startsWith("direct")) {
                  setNotifications((n) => [`Model status: ${parsed.provider_status}`, ...n].slice(0, 5));
                }
              }
            } catch {
              /* skip */
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
  const offline = !telemetry.online;

  return (
    <main
      data-mode={modeKey}
      className="relative min-h-screen overflow-hidden px-4 py-4 text-slate-100 sm:px-6 lg:px-8"
    >
      <div className="scanlines absolute inset-0 opacity-25" />
      <div className="relative z-10 mx-auto grid max-w-7xl gap-4 lg:grid-cols-[300px_1fr_320px]">
        <motion.aside
          {...(mounted ? fade(0) : {})}
          className="hud-panel rounded-lg p-4"
        >
          <div className="flex items-center gap-3 border-b border-[var(--accent)]/20 pb-4">
            <BrainCircuit style={{ color: "var(--accent-strong)" }} />
            <div>
              <p className="text-xs uppercase tracking-[0.28em]" style={{ color: "var(--accent-text)" }}>
                VERONICA
              </p>
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

          <div className="mt-5 rounded-lg border border-white/10 bg-black/20 p-3">
            <div className="mb-3 flex items-center justify-between">
              <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
                <Activity size={16} /> System Monitor
              </p>
              <span
                className={`rounded px-2 py-0.5 text-[10px] font-semibold tracking-[0.18em] ${
                  offline ? "bg-pink-500/20 text-pink-200" : "bg-emerald-500/15 text-emerald-200"
                }`}
              >
                {offline ? "OFFLINE" : "ONLINE"}
              </span>
            </div>
            <div className="space-y-2 text-xs">
              <Row label="Model" value={telemetry.model?.model ?? "—"} />
              <Row
                label="Provider"
                value={telemetry.model?.base_url ?? "—"}
                title={telemetry.model?.base_url}
              />
              <Row
                label="RSS"
                value={telemetry.system ? `${telemetry.system.stats.rss_mb.toFixed(0)} MB` : "—"}
              />
              <Row
                label="Sessions"
                value={telemetry.system?.active_sessions != null ? String(telemetry.system.active_sessions) : "—"}
              />
              <Row
                label="Health latency"
                value={telemetry.latencyMs != null ? `${telemetry.latencyMs} ms` : "—"}
              />
              <Row label="Last reply" value={chatLatency != null ? `${chatLatency} ms` : "—"} />
            </div>
          </div>
        </motion.aside>

        <section className="grid gap-4">
          <motion.div
            {...(mounted ? fade(150) : {})}
            className="hud-panel rounded-lg p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.28em]" style={{ color: "var(--accent-text)" }}>
                  Active Mode: {mode}
                </p>
                <h2 className="mt-1 text-2xl font-semibold sm:text-3xl">Arc command interface</h2>
              </div>
              <div className="rounded-lg border border-[var(--accent)]/30 bg-black/30 px-3 py-2 text-sm">
                <VoiceInterface
                  onCommand={(text) => void sendMessage(text)}
                  speak={latestAssistantReply}
                  busy={busy}
                />
              </div>
            </div>
            <ErrorBoundary name="ArcCore">
              <ArcCore mode={mode} busy={busy} />
            </ErrorBoundary>
            <p className="mx-auto max-w-2xl text-center text-sm text-slate-300">{activeBriefing}</p>
          </motion.div>

          <motion.div
            {...(mounted ? fade(150) : {})}
            className="hud-panel rounded-lg p-4"
          >
            <div className="mb-3 flex items-center justify-between">
              <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
                <TerminalSquare size={16} /> Conversational AI
              </p>
              <span className="text-xs text-slate-400">{busy ? "Thinking" : "Ready"}</span>
            </div>

            <div className="h-[330px] space-y-3 overflow-y-auto pr-1">
              {messages.map((message, index) => (
                <div
                  key={`${message.role}-${index}`}
                  className={`rounded-lg border p-3 text-sm leading-6 ${
                    message.role === "assistant"
                      ? "border-[var(--accent)]/20 bg-[var(--accent)]/[0.06] text-[var(--accent-text)]"
                      : "ml-auto max-w-[86%] border-pink-300/20 bg-pink-400/[0.07] text-pink-50"
                  }`}
                >
                  <p className="mb-1 text-xs uppercase tracking-[0.18em] text-slate-400">
                    {message.role === "assistant" ? "VERONICA" : "COMMANDER"}
                  </p>
                  <span>{message.content}</span>
                  {message.streaming ? <span className="ml-1 inline-block animate-pulse">▍</span> : null}
                </div>
              ))}
            </div>

            <form onSubmit={onSubmit} className="mt-4 flex gap-2">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Veronica, deploy coding mode."
                className="min-w-0 flex-1 rounded-lg border border-[var(--accent)]/20 bg-black/30 px-3 py-3 text-sm text-white outline-none transition placeholder:text-slate-400 focus:border-[var(--accent-strong)]"
              />
              <button
                disabled={busy}
                className="rounded-lg border border-[var(--accent)]/40 bg-[var(--accent)]/15 px-5 py-3 text-sm font-semibold text-[var(--accent-text)] transition hover:bg-[var(--accent)]/25 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Send
              </button>
            </form>
          </motion.div>

          <motion.div {...(mounted ? fade(300) : {})}>
            <ErrorBoundary name="OperationsPanels">
              <OperationsPanels />
            </ErrorBoundary>
          </motion.div>
        </section>

        <motion.aside
          {...(mounted ? fade(300) : {})}
          className="space-y-4"
        >
          <div className="hud-panel rounded-lg p-4">
            <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
              <Code2 size={16} /> Protocols
            </p>
            <div className="space-y-2">
              {starterTasks.map((task) => (
                <button
                  key={task}
                  onClick={() => void sendMessage(`Veronica, ${task.toLowerCase()}.`)}
                  className="w-full rounded-lg border border-white/10 bg-white/[0.03] p-3 text-left text-sm text-slate-200 transition hover:border-[var(--accent)]/40 hover:bg-[var(--accent)]/[0.07]"
                >
                  {task}
                </button>
              ))}
            </div>
          </div>

          <div className="hud-panel rounded-lg p-4">
            <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
              <Shield size={16} /> Security Rules
            </p>
            <div className="space-y-3 text-sm text-slate-300">
              <p>Dangerous actions require confirmation.</p>
              <p>Secrets stay server-side.</p>
              <p>Autonomous steps are logged.</p>
              <p>Shell execution is whitelist-first.</p>
            </div>
          </div>

          <div className="hud-panel rounded-lg p-4">
            <p className="mb-3 flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
              <Bell size={16} /> Live Notifications
            </p>
            <div className="space-y-2">
              {notifications.map((notification, index) => (
                <div
                  key={`${notification}-${index}`}
                  className="rounded-lg border border-white/10 bg-black/20 p-3 text-xs text-slate-300"
                >
                  {notification}
                </div>
              ))}
            </div>
          </div>
        </motion.aside>
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
