"use client";

import { motion } from "framer-motion";
import {
  AlertTriangle,
  Bell,
  BrainCircuit,
  Code2,
  LayoutDashboard,
  Shield,
  TerminalSquare,
  Timer,
  X,
  z
} from "lucide-react";
import React, {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ArcCore } from "@/components/ArcCore";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { OperationsPanels } from "@/components/OperationsPanels";
import { VoiceInterface } from "@/components/VoiceInterface";
import { useMemoryEfficientState } from "@/hooks/useMemoryEfficientState";
import { useMounted } from "@/hooks/useMounted";
import { useTelemetry } from "@/hooks/useTelemetry";

/* ── Markdown renderer ───────────────────────────────────── */
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
    if (line.trim() === "") { nodes.push(<div key={i} className="my-1" />); return; }
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

function fade(delayMs = 0) {
  if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return {};
  return {
    initial: { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: { delay: delayMs / 1000, duration: 0.4, ease: "easeOut" },
  };
}

/* ── Types ───────────────────────────────────────────────── */
type Mode = "JARVIS" | "FRIDAY" | "VERONICA" | "SENTINEL";
type Message = { role: "user" | "assistant"; content: string; streaming?: boolean };

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

const MODE_GLYPHS: Record<Mode, string> = { JARVIS: "J", FRIDAY: "F", VERONICA: "V", SENTINEL: "S" };
const MODE_KEYS: Record<Mode, string> = { JARVIS: "⌥1", FRIDAY: "⌥2", VERONICA: "⌥3", SENTINEL: "⌥4" };

const PROTOCOL_CHIPS = [
  { label: "Draft reply", msg: "Draft a reply to the last important email, professional tone, about 80 words." },
  { label: "Triage inbox", msg: "Summarize and triage my inbox." },
  { label: "Focus 25", msg: "Start a 25-minute focus session." },
  { label: "Sentinel sweep", msg: "Run a security review of the last 24 hours." },
];

/* ── Hooks ───────────────────────────────────────────────── */
function useSparkline(maxLen = 20, base = 40, jitter = 18): number[] {
  const [data, setData] = useState<number[]>(() =>
    Array.from({ length: maxLen }, () => base + Math.random() * jitter)
  );
  useEffect(() => {
    const iv = setInterval(() => {
      setData((prev) => {
        const last = prev[prev.length - 1] ?? base;
        const next = Math.max(8, Math.min(96, last + (Math.random() - 0.5) * 14));
        return [...prev.slice(1), next];
      });
    }, 1200);
    return () => clearInterval(iv);
  }, [base]);
  return data;
}

function useUptime(): string {
  const startRef = useRef<number>(0);
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    startRef.current = Date.now();
    const iv = setInterval(() => setSecs(Math.floor((Date.now() - startRef.current) / 1000)), 1000);
    return () => clearInterval(iv);
  }, []);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/* ── Status Rail ─────────────────────────────────────────── */
function StatusRail({
  mode, uptime, latency, model, sessionId,
}: {
  mode: Mode; uptime: string; latency: number | null | undefined;
  model: string; sessionId: string;
}) {
  return (
    <div className="status-rail">
      <div className="sr-brand">
        <span className="sr-mark" />
        VERONICA · OS
      </div>
      <div className="sr-seg">
        <span className="sr-key">MODE</span>
        <span className="sr-val" style={{ color: "var(--accent-text)" }}>{mode}</span>
      </div>
      <div className="sr-seg hidden sm:flex">
        <span className="sr-key">MODEL</span>
        <span className="sr-val">{model || "qwen2.5:7b"}</span>
      </div>
      <div className="sr-seg hidden md:flex">
        <span className="sr-key">SESSION</span>
        <span className="sr-val">{sessionId.slice(0, 8)}</span>
      </div>
      <div className="sr-seg hidden lg:flex">
        <span className="sr-key">UPTIME</span>
        <span className="sr-val">{uptime}</span>
      </div>
      <div className="sr-seg hidden lg:flex">
        <span className="sr-key">LATENCY</span>
        <span className="sr-val">{latency != null ? `${latency}ms` : "--"}</span>
      </div>
      <div className="sr-spacer" />
      <div className="sr-pill">
        <span className="sr-dot" />
        REACTOR ONLINE
      </div>
    </div>
  );
}

/* ── Footer Rail ─────────────────────────────────────────── */
function FooterRail({
  apiOffline, model,
}: {
  apiOffline: boolean;
  model: Record<string, unknown> | null | undefined;
}) {
  const ollamaUp = model?.running === true;
  return (
    <footer className="footer-rail">
      <div className="fr-group">
        <span><span className={`fr-dot ${apiOffline ? "warn" : "ok"}`} />api · :8000</span>
        <span><span className={`fr-dot ${ollamaUp ? "ok" : "warn"}`} />ollama · :11434</span>
        <span className="hidden sm:inline"><span className="fr-dot ok" />whisper · armed</span>
      </div>
      <div className="fr-group">
        <span>build · v0.7.3-arc</span>
        <span>©2026 VERONICA</span>
      </div>
    </footer>
  );
}

/* ── Telemetry Panel (replaces SystemMonitor) ────────────── */
type SysStats = {
  cpu_percent: number; ram_percent: number; ram_used_gb: number; ram_total_gb: number;
  disk_percent: number; disk_used_gb: number; disk_total_gb: number;
} | null;

function TelemetryPanel({
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

  const cpuBase = stats?.cpu_percent ?? 32;
  const ramBase = stats?.ram_percent ?? 58;
  const cpuSpark = useSparkline(20, cpuBase, 16);
  const ramSpark = useSparkline(20, ramBase, 8);

  React.useEffect(() => {
    if (apiOffline) return;
    const load = () =>
      fetch(`${API}/system/stats`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (d) setStats(d as SysStats); })
        .catch(() => null);
    load();
    const iv = setInterval(load, 10_000);
    return () => clearInterval(iv);
  }, [apiOffline, API]);

  const m = model as Record<string, unknown> | null | undefined;

  const tickColor = (v: number) =>
    v > 85 ? "#f87171" : v > 65 ? "#fb923c" : "var(--accent-strong)";

  return (
    <motion.div {...(mounted ? fade(60) : {})} className="mt-5 rounded-lg border border-white/10 bg-black/20 p-3">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: "var(--accent-text)" }}>
          ◈ Telemetry · live
        </p>
        <span className={`rounded px-2 py-0.5 text-[9px] font-mono font-semibold tracking-[0.15em] ${apiOffline ? "bg-pink-500/20 text-pink-200" : "bg-emerald-500/15 text-emerald-200"
          }`}>
          {apiOffline ? "OFFLINE" : "ONLINE"}
        </span>
      </div>

      <div className="space-y-3">
        <div>
          <div className="mb-1 flex items-baseline justify-between">
            <span className="text-[10px] font-mono tracking-[0.18em] text-slate-500">CPU</span>
            <span className="text-[10px] font-mono text-slate-300">
              {stats ? `${stats.cpu_percent.toFixed(0)}%` : "--"}
            </span>
          </div>
          <div className="spark">
            {cpuSpark.map((v, i) => (
              <div key={i} className="spark-tick" style={{ height: `${v}%`, background: tickColor(v) }} />
            ))}
          </div>
          {m?.model != null && (
            <div className="mt-0.5 truncate text-[9px] font-mono text-slate-600">{String(m.model)}</div>
          )}
        </div>

        <div>
          <div className="mb-1 flex items-baseline justify-between">
            <span className="text-[10px] font-mono tracking-[0.18em] text-slate-500">RAM</span>
            <span className="text-[10px] font-mono text-slate-300">
              {stats ? `${stats.ram_used_gb}/${stats.ram_total_gb} GB` : "--"}
            </span>
          </div>
          <div className="spark">
            {ramSpark.map((v, i) => (
              <div key={i} className="spark-tick" style={{ height: `${v}%`, background: tickColor(v) }} />
            ))}
          </div>
        </div>

        {stats && (
          <div>
            <div className="mb-1 flex items-baseline justify-between">
              <span className="text-[10px] font-mono tracking-[0.18em] text-slate-500">DISK</span>
              <span className="text-[10px] font-mono text-slate-300">
                {stats.disk_used_gb}/{stats.disk_total_gb} GB
              </span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(stats.disk_percent, 100)}%`,
                  background: tickColor(stats.disk_percent),
                }}
              />
            </div>
          </div>
        )}

        <div className="space-y-1.5 border-t border-white/[0.06] pt-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono tracking-[0.18em] text-slate-600">LATENCY</span>
            <span className="text-[10px] font-mono text-slate-400">{latencyMs != null ? `${latencyMs}ms` : "--"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono tracking-[0.18em] text-slate-600">LAST REPLY</span>
            <span className="text-[10px] font-mono text-slate-400">{chatLatency != null ? `${chatLatency}ms` : "--"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono tracking-[0.18em] text-slate-600">OLLAMA</span>
            <span className={`text-[10px] font-mono ${m?.running ? "text-emerald-400" : "text-slate-600"}`}>
              {!m ? "--" : m.running ? "● RUNNING" : "⊘ DOWN"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono tracking-[0.18em] text-slate-600">SESSIONS</span>
            <span className="text-[10px] font-mono text-slate-400">
              {system?.active_sessions != null ? String(system.active_sessions) : "--"}
            </span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

/* ── Security Doctrine Panel ─────────────────────────────── */
type SecRuleKey = "confirm" | "secrets" | "audit" | "shell" | "autoreply";

const SEC_RULES: Array<[SecRuleKey, string]> = [
  ["confirm", "Dangerous actions require confirmation"],
  ["secrets", "Secrets stay server-side"],
  ["audit", "Autonomous steps are logged"],
  ["shell", "Shell execution is whitelist-first"],
  ["autoreply", "Auto-reply to known senders"],
];

function SecurityDoctrinePanel() {
  const [rules, setRules] = useState<Record<SecRuleKey, boolean>>({
    confirm: true, secrets: true, audit: true, shell: true, autoreply: false,
  });
  const toggle = (k: SecRuleKey) => setRules((r) => ({ ...r, [k]: !r[k] }));

  return (
    <div className="space-y-1">
      {SEC_RULES.map(([k, label]) => (
        <div
          key={k}
          onClick={() => toggle(k)}
          className="flex cursor-pointer items-center justify-between gap-2 rounded border border-white/[0.05] bg-black/10 px-2.5 py-2 transition hover:bg-white/[0.03]"
        >
          <span className="text-[11px] text-slate-400">{label}</span>
          <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-mono tracking-[0.12em] transition ${rules[k]
              ? "border-[var(--accent-border)] bg-[var(--accent)]/10 text-[var(--accent-text)]"
              : "border-white/10 bg-transparent text-slate-600"
            }`}>
            {rules[k] ? "ON" : "OFF"}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ── Pomodoro Widget ─────────────────────────────────────── */
function PomodoroWidget({ onSend }: { onSend: (msg: string) => void }) {
  const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const [status, setStatus] = React.useState<{
    active: boolean; label: string; elapsed_seconds: number;
    remaining_seconds: number; percent_done: number;
  } | null>(null);
  const [labelInput, setLabelInput] = React.useState("");

  React.useEffect(() => {
    const load = () =>
      fetch(`${API}/pomodoro/status`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (d) setStatus(d); })
        .catch(() => null);
    load();
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [API]);

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  const start = async () => {
    const label = labelInput.trim() || "Focus session";
    await fetch(`${API}/pomodoro/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, duration_minutes: 25 }),
    });
    setLabelInput("");
    setTimeout(() =>
      fetch(`${API}/pomodoro/status`).then((r) => r.json()).then(setStatus).catch(() => null),
      300);
  };

  const stop = async () => {
    await fetch(`${API}/pomodoro/stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ completed: false }),
    });
    setStatus(null);
  };

  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-3">
      <p className="mb-2 flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: "var(--accent-text)" }}>
        <Timer size={12} /> Focus Timer
      </p>
      {status?.active ? (
        <>
          <p className="mb-1 truncate text-[11px] text-slate-400">{status.label}</p>
          <div className="mb-2 h-1 overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${status.percent_done}%`, background: "var(--accent-strong)" }}
            />
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="font-mono text-slate-200">{fmt(status.remaining_seconds)} left</span>
            <button onClick={() => void stop()} className="text-pink-300 transition hover:text-pink-100">
              Stop
            </button>
          </div>
        </>
      ) : (
        <div className="flex gap-2">
          <input
            value={labelInput}
            onChange={(e) => setLabelInput(e.target.value)}
            placeholder="Task label"
            className="min-w-0 flex-1 rounded border border-white/10 bg-black/30 px-2 py-1 text-xs text-white outline-none transition placeholder:text-slate-600 focus:border-[var(--accent-strong)]"
          />
          <button
            onClick={() => void start()}
            className="rounded border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-2 py-1 text-[10px] font-mono text-[var(--accent-text)] transition hover:bg-[var(--accent)]/20"
          >
            25 min
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Row (telemetry label/value) ─────────────────────────── */
function Row({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="flex items-center justify-between gap-2" title={title}>
      <span className="text-slate-400">{label}</span>
      <span className="truncate text-right text-slate-200" style={{ maxWidth: "60%" }}>{value}</span>
    </div>
  );
}

/* ── Left Panel ──────────────────────────────────────────── */
function LeftPanelContent({
  mode, setMode, apiOffline, telemetry, chatLatency, mounted,
}: {
  mode: Mode;
  setMode: (m: Mode) => void;
  apiOffline: boolean;
  telemetry: {
    model: Record<string, unknown> | null | undefined;
    system: Record<string, unknown> | null | undefined;
    latencyMs: number | null | undefined;
    online: boolean;
  };
  chatLatency: number | null;
  mounted: boolean;
}) {
  return (
    <>
      <div className="flex items-center gap-3 border-b border-[var(--accent)]/20 pb-4">
        <BrainCircuit style={{ color: "var(--accent-strong)" }} />
        <div>
          <p className="text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: "var(--accent-text)" }}>
            VERONICA
          </p>
          <h1 className="text-xl font-semibold">Command OS</h1>
        </div>
      </div>

      <div className="mt-4">
        <p className="mb-2 text-[9px] font-mono uppercase tracking-[0.2em] text-slate-600">
          ◇ Cognitive Mode · 4/4
        </p>
        <div className="space-y-1.5">
          {modes.map((item) => {
            const active = mode === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setMode(item.id)}
                aria-pressed={active}
                className={`flex w-full items-center gap-2.5 rounded-lg border p-2.5 text-left transition ${active
                    ? "mode-active border-[var(--accent-strong)] bg-[var(--accent)]/12 text-white"
                    : "border-white/10 bg-white/[0.03] text-slate-300 hover:border-[var(--accent)]/50"
                  }`}
              >
                <span className={`mode-glyph ${active ? "active" : ""}`}>
                  {MODE_GLYPHS[item.id]}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">{item.label}</span>
                  <span className="text-[10px] text-slate-500">{item.detail}</span>
                </span>
                <span className="hidden shrink-0 text-[9px] font-mono text-slate-600 sm:block">
                  {MODE_KEYS[item.id]}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {mode === "SENTINEL" && (
        <div
          className="mt-3 flex items-center gap-2 rounded-lg border px-3 py-2"
          style={{ color: "var(--accent-strong)", borderColor: "var(--accent-border)", background: "var(--accent-glow)" }}
        >
          <span className="animate-pulse text-xs">&#9679;</span>
          <span className="text-[10px] font-mono uppercase tracking-[0.18em]">THREAT LEVEL: MONITORING</span>
        </div>
      )}

      <TelemetryPanel
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

/* ── Right Panel ─────────────────────────────────────────── */
function RightPanelContent({
  starterTasks: tasks, notifications, busy, sendMessage, mounted, mode,
}: {
  starterTasks: string[];
  notifications: string[];
  busy: boolean;
  sendMessage: (msg: string) => void;
  mounted: boolean;
  mode: Mode;
}) {
  return (
    <>
      <motion.div {...(mounted ? fade(300) : {})} className="hud-panel min-w-0 overflow-hidden rounded-lg p-4">
        <p className="mb-3 flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: "var(--accent-text)" }}>
          <Code2 size={13} /> ◇ Protocols
        </p>
        <div className="space-y-1.5">
          {tasks.map((task) => (
            <button
              key={task}
              onClick={() => void sendMessage(`Veronica, ${task.toLowerCase()}.`)}
              className="flex w-full items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-left text-xs text-slate-300 transition hover:border-[var(--accent)]/40 hover:bg-[var(--accent)]/[0.07] hover:text-slate-100"
            >
              <span className="shrink-0 font-mono text-[var(--accent-dim)]">›_</span>
              <span className="break-words">{task}</span>
            </button>
          ))}
        </div>
      </motion.div>

      <motion.div {...(mounted ? fade(360) : {})} className="hud-panel min-w-0 overflow-hidden rounded-lg p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: "var(--accent-text)" }}>
            <Shield size={13} /> ⊕ Security Doctrine
          </p>
          <span className={`rounded px-1.5 py-0.5 text-[9px] font-mono tracking-[0.12em] ${mode === "SENTINEL"
              ? "border border-[var(--accent-border)] bg-[var(--accent)]/10 text-[var(--accent-text)]"
              : "text-slate-600"
            }`}>
            {mode === "SENTINEL" ? "ELEVATED" : "BASELINE"}
          </span>
        </div>
        <SecurityDoctrinePanel />
      </motion.div>

      <motion.div {...(mounted ? fade(420) : {})} className="hud-panel min-w-0 overflow-hidden rounded-lg p-4">
        <p className="mb-2 flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: "var(--accent-text)" }}>
          <Bell size={13} /> Notifications
        </p>
        <div className="space-y-1">
          {notifications.map((n, i) => (
            <div
              key={`${n}-${i}`}
              className="rounded border border-white/[0.06] bg-black/20 px-2.5 py-1.5 text-[10px] font-mono text-slate-500 break-words"
            >
              <span className="mr-1.5" style={{ color: "var(--accent-dim)" }}>›</span>{n}
            </div>
          ))}
        </div>
      </motion.div>
    </>
  );
}

/* ── Home ────────────────────────────────────────────────── */
export default function Home() {
  const mounted = useMounted();
  const uptime = useUptime();
  const [mode, setMode] = useState<Mode>("JARVIS");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [chatLatency, setChatLatency] = useState<number | null>(null);
  const [showLeft, setShowLeft] = useState(false);
  const [showRight, setShowRight] = useState(false);

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
        content: "Sir, VERONICA is online. Command center initialized, modes armed, voice pipeline standing by. Subtle, tasteful, mildly overqualified.",
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

  /* ⌥1–4 mode switching */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!e.altKey) return;
      const idx = ["1", "2", "3", "4"].indexOf(e.key);
      if (idx >= 0) setMode(modes[idx]!.id);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const activeBriefing = useMemo(() => {
    if (mode === "FRIDAY") return "Productivity routing active. Calendar, reminders, planning, drafting are prioritized.";
    if (mode === "VERONICA") return "Emergency reasoning active. Simulation, risk ranking, decisive recommendations are prioritized.";
    if (mode === "SENTINEL") return "Security monitoring active. Permissions, secrets, suspicious actions are under review.";
    return "General intelligence active. Context, tools, concise technical guidance are prioritized.";
  }, [mode]);

  const latestAssistantReply = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
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
          headers: { "Content-Type": "application/json", "X-Session-ID": sessionId.current },
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
                if (parsed.protocol) setNotifications((n) => [`Protocol engaged: ${parsed.protocol}`, ...n].slice(0, 5));
                if (parsed.provider_status && parsed.provider_status !== "ok" && !String(parsed.provider_status).startsWith("direct")) {
                  setNotifications((n) => [`Model status: ${parsed.provider_status}`, ...n].slice(0, 5));
                }
              }
            } catch { /* skip malformed */ }
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
          content: "Sir, the backend is not responding. Frontend remains operational; bring the FastAPI service up on port 8000.",
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
  const apiOffline = !telemetry.online;
  const modelOffline = telemetry.online && telemetry.model != null && !telemetry.model.configured;
  const noKeySet = modelOffline && telemetry.model != null && !telemetry.model.provider_key_present;
  const allRateLimited = modelOffline && telemetry.model != null && telemetry.model.provider_key_present;
  const modelStr = telemetry.model?.model ? String(telemetry.model.model) : "qwen2.5:7b";

  return (
    <div data-mode={modeKey} className="flex min-h-screen flex-col">
      <StatusRail
        mode={mode}
        uptime={uptime}
        latency={chatLatency ?? telemetry.latencyMs}
        model={modelStr}
        sessionId={sessionId.current}
      />

      <main className="relative flex-1 overflow-x-hidden px-3 py-3 text-slate-100 sm:px-4 sm:py-4">
        <div className="scanlines absolute inset-0 opacity-25" />
        <div className="scan-line" />

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
            <span className="text-[10px] font-mono font-semibold tracking-[0.18em]" style={{ color: "var(--accent-text)" }}>{mode}</span>
          </div>
          <button
            onClick={() => { setShowRight(true); setShowLeft(false); }}
            className="flex items-center gap-2 rounded-lg border border-[var(--accent)]/30 bg-black/40 px-3 py-2 text-xs text-[var(--accent-text)] backdrop-blur"
          >
            <LayoutDashboard size={14} /> Tools
          </button>
        </div>

        {/* Mobile left drawer */}
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

        {/* Mobile right drawer */}
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
                mode={mode}
              />
            </motion.div>
          </div>
        )}

        <div className="app-grid relative z-10 mx-auto max-w-7xl">
          {/* Left panel — desktop */}
          <motion.aside {...(mounted ? fade(0) : {})} className="panel-left hud-panel rounded-lg p-4">
            <LeftPanelContent mode={mode} setMode={setMode} apiOffline={apiOffline} telemetry={telemetry} chatLatency={chatLatency} mounted={mounted} />
          </motion.aside>

          {/* Center */}
          <section className="app-grid-center grid gap-4">
            <motion.div {...(mounted ? fade(150) : {})} className="hud-panel rounded-lg p-3 sm:p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: "var(--accent-text)" }}>
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
              <p className="mx-auto max-w-2xl text-center text-xs text-slate-400 sm:text-sm">{activeBriefing}</p>
            </motion.div>

            <motion.div {...(mounted ? fade(210) : {})} className="hud-panel rounded-lg p-3 sm:p-4">
              <div className="mb-3 flex items-center justify-between">
                <p className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: "var(--accent-text)" }}>
                  <TerminalSquare size={14} /> Conversational Stream
                </p>
                <span className="text-[10px] font-mono text-slate-500">{busy ? "STREAMING…" : "READY"}</span>
              </div>

              <div className="chat-scroll space-y-2 overflow-y-auto pr-1">
                {messages.map((message, index) => (
                  <div
                    key={`${message.role}-${index}`}
                    className={`msg-in rounded-lg border p-3 text-sm leading-6 ${message.role === "assistant"
                        ? "border-[var(--accent)]/20 bg-[var(--accent)]/[0.06] text-[var(--accent-text)]"
                        : "ml-auto max-w-[90%] border-pink-300/20 bg-pink-400/[0.07] text-pink-50"
                      }`}
                  >
                    <p className="mb-1 text-[10px] font-mono uppercase tracking-[0.18em] text-slate-500">
                      {message.role === "assistant" ? "VERONICA" : "COMMANDER"}
                    </p>
                    <div className="min-w-0 break-words">{renderMarkdown(message.content)}</div>
                    {message.streaming && index === messages.length - 1 && (
                      <span
                        className="ml-0.5 inline-block h-3.5 w-0.5 animate-pulse align-middle"
                        style={{ background: "var(--accent-strong)" }}
                      />
                    )}
                  </div>
                ))}
              </div>

              {/* Protocol chips */}
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {PROTOCOL_CHIPS.map((chip) => (
                  <button
                    key={chip.label}
                    onClick={() => void sendMessage(chip.msg)}
                    disabled={busy}
                    className="rounded border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[10px] text-slate-400 transition hover:border-[var(--accent)]/30 hover:bg-[var(--accent)]/[0.06] hover:text-slate-200 disabled:pointer-events-none disabled:opacity-40"
                  >
                    <span className="mr-1 font-mono" style={{ color: "var(--accent-dim)" }}>›_</span>
                    {chip.label}
                  </button>
                ))}
              </div>

              <form onSubmit={onSubmit} className="mt-2.5 flex gap-2">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Veronica, deploy coding mode."
                  className="min-w-0 flex-1 rounded-lg border border-[var(--accent)]/20 bg-black/30 px-3 py-2.5 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-[var(--accent-strong)] sm:py-3"
                />
                <button
                  disabled={busy}
                  className="rounded-lg border border-[var(--accent)]/40 bg-[var(--accent)]/15 px-4 py-2.5 text-sm font-semibold text-[var(--accent-text)] transition hover:bg-[var(--accent)]/25 disabled:cursor-not-allowed disabled:opacity-50 sm:px-5 sm:py-3"
                >
                  Send
                </button>
              </form>
            </motion.div>

            <motion.div {...(mounted ? fade(270) : {})} className="min-w-0 overflow-hidden">
              <ErrorBoundary name="OperationsPanels">
                <OperationsPanels />
              </ErrorBoundary>
            </motion.div>
          </section>

          {/* Right panel — desktop */}
          <aside className="panel-right min-w-0 overflow-hidden space-y-4">
            <RightPanelContent
              starterTasks={starterTasks}
              notifications={notifications}
              busy={busy}
              sendMessage={sendMessage}
              mounted={mounted}
              mode={mode}
            />
          </aside>
        </div>
      </main>

      <FooterRail apiOffline={apiOffline} model={telemetry.model} />
    </div>
  );
}
