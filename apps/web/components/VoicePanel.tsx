"use client";

import { useEffect, useRef, useState } from "react";

type Stage = "idle" | "detected" | "transcribed" | "replied";

interface WakeEvent {
  stage: Stage;
  text: string;
  response: string;
}

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STAGE_LABEL: Record<Stage, string> = {
  idle:        "Listening…",
  detected:    "Wake word detected — speak your command",
  transcribed: "Processing…",
  replied:     "Replied",
};

const STAGE_COLOR: Record<Stage, string> = {
  idle:        "text-zinc-500",
  detected:    "text-cyan-400",
  transcribed: "text-yellow-400",
  replied:     "text-emerald-400",
};

const PULSE: Record<Stage, boolean> = {
  idle: false, detected: true, transcribed: true, replied: false,
};

export default function VoicePanel() {
  const [event, setEvent] = useState<WakeEvent>({ stage: "idle", text: "", response: "" });
  const [history, setHistory] = useState<{ command: string; reply: string }[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    function connect() {
      const es = new EventSource(`${API}/wake/stream`);
      esRef.current = es;

      es.onopen = () => setConnected(true);

      es.onmessage = (e) => {
        try {
          const data: WakeEvent = JSON.parse(e.data);
          setEvent(data);
          if (data.stage === "replied" && data.text && data.response) {
            setHistory((h) => [{ command: data.text, reply: data.response }, ...h].slice(0, 20));
          }
        } catch {
          /* ignore malformed events */
        }
      };

      es.onerror = () => {
        setConnected(false);
        es.close();
        setTimeout(connect, 4000);
      };
    }

    connect();
    return () => esRef.current?.close();
  }, []);

  const stage = event.stage as Stage;

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-300 tracking-wide uppercase">
          Voice — Hey Jarvis
        </h2>
        <span className={`flex items-center gap-1.5 text-xs ${connected ? "text-emerald-400" : "text-zinc-600"}`}>
          <span className={`inline-block h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-zinc-600"}`} />
          {connected ? "Live" : "Disconnected"}
        </span>
      </div>

      {/* Current stage */}
      <div className="flex items-center gap-3">
        <div className="relative flex h-8 w-8 items-center justify-center">
          {/* Mic icon */}
          <svg className={`h-5 w-5 ${STAGE_COLOR[stage]}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
          </svg>
          {PULSE[stage] && (
            <span className="absolute inset-0 rounded-full animate-ping bg-cyan-500 opacity-25" />
          )}
        </div>
        <span className={`text-sm font-medium ${STAGE_COLOR[stage]}`}>
          {STAGE_LABEL[stage]}
        </span>
      </div>

      {/* Current command being processed */}
      {(stage === "transcribed" || stage === "replied") && event.text && (
        <div className="rounded-lg bg-zinc-800 px-3 py-2 text-xs text-zinc-300 space-y-1">
          <p className="text-zinc-500 uppercase tracking-wide text-[10px]">You said</p>
          <p>{event.text}</p>
          {stage === "replied" && event.response && (
            <>
              <p className="text-zinc-500 uppercase tracking-wide text-[10px] pt-1">Veronica</p>
              <p className="text-emerald-300">{event.response}</p>
            </>
          )}
        </div>
      )}

      {/* History */}
      {history.length > 0 && (
        <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
          <p className="text-[10px] uppercase tracking-wide text-zinc-600">Recent</p>
          {history.map((h, i) => (
            <div key={i} className="rounded-lg bg-zinc-800/60 px-3 py-2 text-xs space-y-1">
              <p className="text-zinc-400">{h.command}</p>
              <p className="text-emerald-400/80">{h.reply}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
