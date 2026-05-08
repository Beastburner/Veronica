"use client";

import { useEffect, useRef, useState } from "react";
import { Music, SkipBack, SkipForward, Play, Pause } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type SpotifyStatus = { connected: boolean; configured: boolean };

type TrackInfo = {
  playing: boolean;
  track: string | null;
  artist: string | null;
  album: string | null;
  progress_ms: number | null;
  duration_ms: number | null;
  volume: number | null;
};

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...opts });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function msToTime(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export function SpotifyPanel() {
  const [status, setStatus] = useState<SpotifyStatus | null>(null);
  const [track, setTrack] = useState<TrackInfo | null>(null);
  const [volume, setVolume] = useState(50);
  const [volumeChanging, setVolumeChanging] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const btn =
    "rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-3 py-1.5 text-xs text-[var(--accent-text)] hover:bg-[var(--accent)]/20 transition disabled:opacity-50";

  async function loadStatus() {
    try {
      const s = await apiFetch<SpotifyStatus>("/spotify/status");
      setStatus(s);
    } catch {
      // silent
    }
  }

  async function loadTrack() {
    try {
      const data = await apiFetch<{ ok: boolean; result?: TrackInfo; error?: string }>("/spotify/current");
      if (data.ok && data.result) {
        setTrack(data.result);
        if (data.result.volume != null) setVolume(data.result.volume);
      }
    } catch {
      // silent
    }
  }

  useEffect(() => {
    void loadStatus();
  }, []);

  useEffect(() => {
    if (!status?.connected) return;
    void loadTrack();
    intervalRef.current = setInterval(() => void loadTrack(), 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [status?.connected]);

  async function doAction(path: string, method = "POST") {
    if (actionBusy) return;
    setActionBusy(true);
    setError(null);
    try {
      await apiFetch(path, { method });
      await loadTrack();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleVolumeChange(v: number) {
    setVolume(v);
    if (volumeChanging) return;
    setVolumeChanging(true);
    setTimeout(async () => {
      try {
        await apiFetch("/spotify/volume", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ volume_pct: v }),
        });
      } catch {
        // silent
      }
      setVolumeChanging(false);
    }, 400);
  }

  const progress = track?.progress_ms != null && track?.duration_ms
    ? (track.progress_ms / track.duration_ms) * 100
    : 0;

  if (!status) {
    return (
      <div className="hud-panel rounded-lg p-4">
        <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <Music size={16} /> Spotify
        </p>
        <p className="mt-3 text-sm text-slate-400">Loading…</p>
      </div>
    );
  }

  if (!status.configured) {
    return (
      <div className="hud-panel rounded-lg p-4 space-y-3">
        <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <Music size={16} /> Spotify
        </p>
        <p className="text-sm text-slate-400">
          Spotify is not configured. Add <code className="text-slate-200">SPOTIFY_CLIENT_ID</code> to your{" "}
          <code className="text-slate-200">.env</code>.
        </p>
      </div>
    );
  }

  if (!status.connected) {
    return (
      <div className="hud-panel rounded-lg p-4 space-y-3">
        <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <Music size={16} /> Spotify
        </p>
        <p className="text-sm text-slate-400">Connect your Spotify account to control playback.</p>
        <a
          href={`${API_URL}/oauth/spotify/start`}
          className="inline-block rounded-lg border border-emerald-400/40 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-300 hover:bg-emerald-400/20 transition"
        >
          Connect Spotify
        </a>
      </div>
    );
  }

  return (
    <div className="hud-panel rounded-lg p-4 space-y-4">
      <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
        <Music size={16} /> Spotify
      </p>

      {error && (
        <div className="rounded-lg border border-pink-300/40 bg-pink-400/10 px-3 py-2 text-sm text-pink-200">
          {error}
        </div>
      )}

      {track?.track ? (
        <div className="space-y-3">
          <div>
            <p className="text-sm font-semibold text-slate-100 truncate">{track.track}</p>
            <p className="text-xs text-slate-400 truncate">{track.artist}</p>
            {track.album && <p className="text-xs text-slate-500 truncate">{track.album}</p>}
          </div>

          <div className="space-y-1">
            <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{ width: `${progress}%`, background: "var(--accent)" }}
              />
            </div>
            <div className="flex justify-between text-xs text-slate-500">
              <span>{track.progress_ms != null ? msToTime(track.progress_ms) : "—"}</span>
              <span>{track.duration_ms != null ? msToTime(track.duration_ms) : "—"}</span>
            </div>
          </div>

          <div className="flex items-center justify-center gap-3">
            <button
              onClick={() => void doAction("/spotify/prev")}
              disabled={actionBusy}
              className={btn}
              title="Previous"
            >
              <SkipBack size={14} />
            </button>
            <button
              onClick={() => void doAction("/spotify/play-pause")}
              disabled={actionBusy}
              className="rounded-full border border-[var(--accent)]/40 bg-[var(--accent)]/20 p-2 text-[var(--accent-text)] hover:bg-[var(--accent)]/30 transition disabled:opacity-50"
              title={track.playing ? "Pause" : "Play"}
            >
              {track.playing ? <Pause size={16} /> : <Play size={16} />}
            </button>
            <button
              onClick={() => void doAction("/spotify/next")}
              disabled={actionBusy}
              className={btn}
              title="Next"
            >
              <SkipForward size={14} />
            </button>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400 w-8 text-right">{volume}%</span>
            <input
              type="range"
              min={0}
              max={100}
              value={volume}
              onChange={(e) => void handleVolumeChange(Number(e.target.value))}
              className="flex-1 h-1.5 rounded-full accent-[var(--accent)] bg-white/10 cursor-pointer"
            />
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-400">Nothing playing.</p>
          <button
            onClick={() => void doAction("/spotify/play-pause")}
            disabled={actionBusy}
            className={btn}
          >
            <Play size={14} className="inline" /> Play
          </button>
        </div>
      )}
    </div>
  );
}
