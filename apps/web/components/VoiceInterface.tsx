"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Mic, MicOff, Square, Volume2, VolumeX } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type VoiceInterfaceProps = {
  onCommand: (text: string) => void;
  speak: string;
  busy?: boolean;
  onRecordingChange?: (recording: boolean) => void;
};

type Phase = "idle" | "recording" | "transcribing" | "denied" | "unavailable" | "error";

function pickMimeType(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  for (const type of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type)) return type;
  }
  return "";
}

function suffixFor(mimeType: string): string {
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("mp4")) return "m4a";
  return "webm";
}

export function VoiceInterface({ onCommand, speak, busy, onRecordingChange }: VoiceInterfaceProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [lastHeard, setLastHeard] = useState("");
  const [speaking, setSpeaking] = useState(false);
  const [muted, setMuted] = useState(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cancelledRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lastSpokenRef = useRef("");

  const cleanupStream = useCallback(() => {
    if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    recorderRef.current = null;
    chunksRef.current = [];
  }, []);

  const start = useCallback(async () => {
    setErrorText(null);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setPhase("unavailable");
      setErrorText("This browser does not expose a microphone API.");
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 48000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch (err: unknown) {
      const e = err as { name?: string };
      if (e?.name === "NotAllowedError" || e?.name === "SecurityError") {
        setPhase("denied");
        setErrorText("Microphone blocked. Allow it from the address-bar lock icon.");
      } else {
        setPhase("error");
        setErrorText("Could not open microphone.");
      }
      return;
    }

    const mimeType = pickMimeType();
    let recorder: MediaRecorder;
    try {
      const opts: MediaRecorderOptions = { audioBitsPerSecond: 128000 };
      if (mimeType) opts.mimeType = mimeType;
      recorder = new MediaRecorder(stream, opts);
    } catch {
      setPhase("error");
      setErrorText("MediaRecorder failed to initialize.");
      stream.getTracks().forEach((t) => t.stop());
      return;
    }

    streamRef.current = stream;
    recorderRef.current = recorder;
    chunksRef.current = [];
    cancelledRef.current = false;

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunksRef.current.push(event.data);
    };

    recorder.onstop = async () => {
      const collected = chunksRef.current;
      const cancelled = cancelledRef.current;
      const recorderMime = recorder.mimeType || mimeType || "audio/webm";
      cleanupStream();

      if (cancelled) {
        setPhase("idle");
        onRecordingChange?.(false);
        return;
      }

      const blob = new Blob(collected, { type: recorderMime });
      if (blob.size < 800) {
        setPhase("idle");
        setErrorText("That was too short, try again.");
        return;
      }

      setPhase("transcribing");
      const form = new FormData();
      form.append("audio", blob, `clip.${suffixFor(recorderMime)}`);

      try {
        const response = await fetch(`${API_URL}/transcribe`, { method: "POST", body: form });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as { text?: string };
        const text = (payload.text ?? "").trim();
        setPhase("idle");
        onRecordingChange?.(false);
        if (text) {
          setLastHeard(text);
          onCommand(text);
        } else {
          setErrorText("No speech detected. Try again, a bit louder.");
        }
      } catch (err: unknown) {
        setPhase("error");
        onRecordingChange?.(false);
        setErrorText(err instanceof Error && err.message.length < 120 ? err.message : "Transcription failed.");
        window.setTimeout(() => setPhase("idle"), 2200);
      }
    };

    recorder.onerror = () => {
      setPhase("error");
      setErrorText("Recording error.");
      cleanupStream();
    };

    recorder.start();
    setPhase("recording");
    setElapsed(0);
    elapsedTimerRef.current = setInterval(() => setElapsed((t) => t + 1), 1000);
    onRecordingChange?.(true);
  }, [cleanupStream, onCommand, onRecordingChange]);

  const stop = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      cancelledRef.current = false;
      try { recorderRef.current.stop(); } catch { /* noop */ }
    }
  }, []);

  const cancel = useCallback(() => {
    cancelledRef.current = true;
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      try { recorderRef.current.stop(); } catch { /* noop */ }
    }
    setPhase("idle");
    setErrorText(null);
  }, []);

  useEffect(() => {
    return () => {
      cancelledRef.current = true;
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        try { recorderRef.current.stop(); } catch { /* noop */ }
      }
      cleanupStream();
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      if (typeof window !== "undefined") {
        window.speechSynthesis?.cancel();
      }
    };
  }, [cleanupStream]);

  // ── TTS ──────────────────────────────────────────────────────────────────

  const playBrowserTTS = useCallback((text: string) => {
    const synthesis = typeof window !== "undefined" ? window.speechSynthesis : undefined;
    if (!synthesis) {
      setSpeaking(false);
      return;
    }
    synthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    synthesis.speak(utterance);
  }, []);

  const playElevenLabs = useCallback(async (text: string): Promise<boolean> => {
    try {
      const response = await fetch(`${API_URL}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) return false;
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => {
        setSpeaking(false);
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        setSpeaking(false);
        URL.revokeObjectURL(url);
      };
      await audio.play();
      return true;
    } catch {
      return false;
    }
  }, []);

  useEffect(() => {
    const trimmed = speak.trim();
    if (!trimmed || trimmed === lastSpokenRef.current || muted) return;
    lastSpokenRef.current = trimmed;
    setSpeaking(true);

    void (async () => {
      const ok = await playElevenLabs(trimmed);
      if (!ok) playBrowserTTS(trimmed);
    })();
  }, [speak, muted, playElevenLabs, playBrowserTTS]);

  const stopSpeaking = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    setSpeaking(false);
  }, []);

  // ── Render ───────────────────────────────────────────────────────────────

  const recording = phase === "recording";
  const transcribing = phase === "transcribing";

  let label = "Click to talk";
  if (busy) label = "Veronica thinking...";
  else if (transcribing) label = "Transcribing...";
  else if (recording) label = `Recording ${elapsed}s, click to send`;
  else if (phase === "denied") label = "Mic blocked";
  else if (phase === "unavailable") label = "Mic unavailable";

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => (recording ? stop() : start())}
          disabled={(phase === "unavailable" || transcribing || busy) && !recording}
          className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
            recording
              ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/15 text-white animate-pulse"
              : transcribing
              ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent-text)]"
              : "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent-text)] hover:bg-[var(--accent)]/20"
          }`}
        >
          {phase === "denied" || phase === "unavailable" ? (
            <MicOff size={14} />
          ) : transcribing || busy ? (
            <Loader2 size={14} className="animate-spin" />
          ) : recording ? (
            <Square size={14} />
          ) : (
            <Mic size={14} />
          )}
          <span>{label}</span>
        </button>
        {recording ? (
          <button
            type="button"
            onClick={cancel}
            className="rounded-lg border border-white/15 bg-black/30 px-2 py-1 text-[10px] text-slate-300 hover:border-white/30"
          >
            Cancel
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => {
            if (speaking) stopSpeaking();
            setMuted((m) => !m);
          }}
          title={muted ? "Unmute voice output" : "Mute voice output"}
          className="ml-auto flex items-center gap-1.5 rounded-lg border border-white/15 bg-black/30 px-2 py-1 text-[11px] text-slate-300 hover:border-white/30"
        >
          {muted ? <VolumeX size={12} /> : <Volume2 size={12} />}
          {speaking ? "Speaking" : muted ? "Muted" : "Voice on"}
        </button>
      </div>
      {lastHeard ? (
        <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">
          Heard: <span className="text-slate-200 normal-case tracking-normal">{lastHeard}</span>
        </p>
      ) : null}
      {errorText ? <p className="text-[11px] text-pink-200">{errorText}</p> : null}
    </div>
  );
}
