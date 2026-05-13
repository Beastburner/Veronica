/* VERONICA — improved command center */
const { useState, useEffect, useRef, useMemo, useCallback } = React;

/* ── Modes ────────────────────────────────────────────────── */
const MODES = [
  { id: "jarvis",   label: "JARVIS",   sub: "General intelligence",   glyph: "J", key: "⌥1", briefing: "General intelligence active. Context, tools, concise technical guidance prioritized." },
  { id: "friday",   label: "FRIDAY",   sub: "Productivity control",   glyph: "F", key: "⌥2", briefing: "Productivity routing active. Calendar, reminders, drafting and planning prioritized." },
  { id: "veronica", label: "VERONICA", sub: "Problem response",       glyph: "V", key: "⌥3", briefing: "Emergency reasoning active. Simulation, risk ranking, decisive recommendations prioritized." },
  { id: "sentinel", label: "SENTINEL", sub: "Security watch",         glyph: "S", key: "⌥4", briefing: "Security monitoring active. Permissions, secrets, suspicious actions under review." },
];

/* ── Neural mesh data (seeded) ─────────────────────────── */
function seededRand(seed) {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

const NEURAL_NODES = (() => {
  const r = seededRand(7);
  const out = [];
  const cx = 160, cy = 160;
  // place clusters: 3 lobes for a brain-ish silhouette
  const lobes = [
    { x: 0,   y: -8,  rx: 78, ry: 64, n: 22 }, // main
    { x: -32, y: 18,  rx: 28, ry: 24, n: 8  }, // left fold
    { x: 32,  y: 18,  rx: 28, ry: 24, n: 8  }, // right fold
  ];
  for (const lobe of lobes) {
    let placed = 0, guard = 0;
    while (placed < lobe.n && guard++ < 800) {
      // polar sample biased toward center
      const t = r() * Math.PI * 2;
      const rho = Math.sqrt(r()) * 0.95;
      const x = lobe.x + Math.cos(t) * lobe.rx * rho;
      const y = lobe.y + Math.sin(t) * lobe.ry * rho;
      // reject if too close to an existing node
      let ok = true;
      for (const p of out) {
        if ((p.x - (cx + x)) ** 2 + (p.y - (cy + y)) ** 2 < 12 ** 2) { ok = false; break; }
      }
      if (ok) {
        out.push({ id: out.length, x: cx + x, y: cy + y, size: 1 + r() * 1.6 });
        placed++;
      }
    }
  }
  return out;
})();

const NEURAL_EDGES = (() => {
  const edges = [];
  const seen = new Set();
  for (let i = 0; i < NEURAL_NODES.length; i++) {
    const a = NEURAL_NODES[i];
    const cands = NEURAL_NODES
      .map((b, j) => (j !== i ? { j, d2: (a.x - b.x) ** 2 + (a.y - b.y) ** 2 } : null))
      .filter(Boolean)
      .sort((x, y) => x.d2 - y.d2)
      .slice(0, 3 + (i % 2)); // 3–4 neighbors
    for (const n of cands) {
      const k = i < n.j ? `${i}-${n.j}` : `${n.j}-${i}`;
      if (seen.has(k)) continue;
      if (n.d2 > 60 * 60) continue; // skip very long edges
      seen.add(k);
      edges.push({ a: i, b: n.j, len: Math.sqrt(n.d2) });
    }
  }
  return edges;
})();

// pick a handful of edges as "active data conduits" for traveling pulses
const PULSE_EDGES = (() => {
  const r = seededRand(99);
  const picks = [];
  while (picks.length < 9) {
    const e = NEURAL_EDGES[Math.floor(r() * NEURAL_EDGES.length)];
    if (e && !picks.includes(e)) picks.push(e);
  }
  return picks;
})();

/* ── Neural Core SVG ──────────────────────────────────── */
function NeuralCore({ busy }) {
  return (
    <svg viewBox="0 0 320 320" aria-hidden="true">
      <defs>
        <radialGradient id="nc-core" cx="50%" cy="50%" r="50%">
          <stop offset="0%"  stopColor="var(--accent-strong)" stopOpacity="1"   />
          <stop offset="22%" stopColor="var(--accent-strong)" stopOpacity="0.65"/>
          <stop offset="55%" stopColor="var(--accent-strong)" stopOpacity="0.12"/>
          <stop offset="100%" stopColor="var(--accent-strong)" stopOpacity="0"  />
        </radialGradient>
        <radialGradient id="nc-halo" cx="50%" cy="50%" r="50%">
          <stop offset="0%"  stopColor="var(--accent-strong)" stopOpacity="0.18" />
          <stop offset="65%" stopColor="var(--accent-strong)" stopOpacity="0.04" />
          <stop offset="100%" stopColor="var(--accent-strong)" stopOpacity="0"   />
        </radialGradient>
        <linearGradient id="nc-sweep" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"   stopColor="var(--accent-strong)" stopOpacity="0"   />
          <stop offset="55%"  stopColor="var(--accent-strong)" stopOpacity="0.55"/>
          <stop offset="100%" stopColor="var(--accent-strong)" stopOpacity="0"   />
        </linearGradient>
        <radialGradient id="nc-radar" cx="100%" cy="50%" r="100%">
          <stop offset="0%"   stopColor="var(--accent-strong)" stopOpacity="0.45" />
          <stop offset="60%"  stopColor="var(--accent-strong)" stopOpacity="0.12" />
          <stop offset="100%" stopColor="var(--accent-strong)" stopOpacity="0"    />
        </radialGradient>
        <filter id="nc-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="1.6" result="b" />
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>

      {/* halo behind everything */}
      <circle cx="160" cy="160" r="155" fill="url(#nc-halo)" />

      {/* outermost faint ring */}
      <circle cx="160" cy="160" r="150" fill="none" stroke="var(--accent-border)" strokeWidth="0.5" opacity="0.6" />

      {/* outer tick ring — 96 ticks, every 8th is long+labeled */}
      <g style={{ transformOrigin: "160px 160px", animation: "rotate-cw 38s linear infinite" }}>
        {Array.from({ length: 96 }).map((_, i) => {
          const angle = (i / 96) * Math.PI * 2;
          const isMajor = i % 8 === 0;
          const isMid = i % 4 === 0;
          const r1 = 144;
          const r2 = isMajor ? 128 : isMid ? 135 : 139;
          const x1 = 160 + Math.cos(angle) * r1, y1 = 160 + Math.sin(angle) * r1;
          const x2 = 160 + Math.cos(angle) * r2, y2 = 160 + Math.sin(angle) * r2;
          return (
            <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke="var(--accent-dim)"
                  strokeWidth={isMajor ? 1.1 : isMid ? 0.7 : 0.5}
                  opacity={isMajor ? 0.85 : isMid ? 0.55 : 0.3} />
          );
        })}
        {/* labeled cardinal degrees */}
        {Array.from({ length: 8 }).map((_, i) => {
          const angle = (i / 8) * Math.PI * 2 - Math.PI / 2;
          const r = 121;
          const x = 160 + Math.cos(angle) * r, y = 160 + Math.sin(angle) * r;
          const deg = String(i * 45).padStart(3, "0");
          return (
            <text key={i} x={x} y={y} textAnchor="middle" dominantBaseline="middle"
                  fontFamily="JetBrains Mono, monospace" fontSize="6.5"
                  fill="var(--accent-text)" opacity="0.75" letterSpacing="1.5">{deg}</text>
          );
        })}
      </g>

      {/* counter-rotating segmented arcs */}
      <g style={{ transformOrigin: "160px 160px", animation: "rotate-ccw 22s linear infinite" }}>
        <path d="M 50 160 A 110 110 0 0 1 110 65"  fill="none" stroke="var(--accent-strong)" strokeWidth="1.4" opacity="0.7" />
        <path d="M 270 160 A 110 110 0 0 1 210 255" fill="none" stroke="var(--accent-strong)" strokeWidth="1.4" opacity="0.7" />
        <path d="M 110 65 A 110 110 0 0 1 160 50"  fill="none" stroke="var(--accent-strong)" strokeWidth="0.8" opacity="0.45" />
        <path d="M 210 255 A 110 110 0 0 1 160 270" fill="none" stroke="var(--accent-strong)" strokeWidth="0.8" opacity="0.45" />
      </g>

      {/* segmented data ring — dashed */}
      <circle cx="160" cy="160" r="118" fill="none"
              stroke="var(--accent-border)" strokeWidth="1"
              strokeDasharray="3 7" opacity="0.7"
              style={{ transformOrigin: "160px 160px", animation: "rotate-cw 26s linear infinite" }} />

      {/* radar sweep */}
      <g style={{ transformOrigin: "160px 160px", animation: "rotate-cw 4.5s linear infinite" }}>
        <path d="M 160 160 L 160 50 A 110 110 0 0 1 245 95 Z"
              fill="url(#nc-radar)" opacity="0.65" />
        <line x1="160" y1="160" x2="160" y2="48" stroke="var(--accent-strong)" strokeWidth="1.4" opacity="0.85" />
      </g>

      {/* mid hex frame */}
      <g style={{ transformOrigin: "160px 160px" }}>
        <polygon points="160,72 246,116 246,204 160,248 74,204 74,116"
                 fill="none" stroke="var(--accent-strong)" strokeWidth="1" opacity="0.5">
          <animate attributeName="opacity" values="0.35;0.7;0.35" dur="4.2s" repeatCount="indefinite" />
        </polygon>
        <polygon points="160,86 232,122 232,198 160,234 88,198 88,122"
                 fill="none" stroke="var(--accent-strong)" strokeWidth="0.6" opacity="0.32" />
      </g>

      {/* neural mesh — edges first, nodes on top */}
      <g opacity="0.6">
        {NEURAL_EDGES.map((e, i) => {
          const a = NEURAL_NODES[e.a], b = NEURAL_NODES[e.b];
          const dur = 2 + (i % 5) * 0.7;
          const delay = (i * 0.13) % 4;
          return (
            <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke="var(--accent-strong)" strokeWidth="0.6">
              <animate attributeName="opacity" values="0.12;0.65;0.12"
                       dur={`${dur}s`} begin={`${delay}s`} repeatCount="indefinite" />
            </line>
          );
        })}
      </g>

      {/* traveling pulses along selected edges */}
      <g>
        {PULSE_EDGES.map((e, i) => {
          const a = NEURAL_NODES[e.a], b = NEURAL_NODES[e.b];
          const pathId = `pulse-${i}`;
          const dur = 1.4 + (i % 4) * 0.4;
          return (
            <g key={i}>
              <path id={pathId} d={`M ${a.x} ${a.y} L ${b.x} ${b.y}`} fill="none" stroke="none" />
              <circle r="1.6" fill="var(--accent-strong)" filter="url(#nc-glow)">
                <animateMotion dur={`${dur}s`} repeatCount="indefinite" begin={`${i * 0.2}s`}>
                  <mpath href={`#${pathId}`} />
                </animateMotion>
                <animate attributeName="opacity" values="0;1;1;0" dur={`${dur}s`} begin={`${i * 0.2}s`} repeatCount="indefinite" />
              </circle>
            </g>
          );
        })}
      </g>

      {/* nodes */}
      <g filter="url(#nc-glow)">
        {NEURAL_NODES.map((n) => (
          <circle key={n.id} cx={n.x} cy={n.y} r={n.size} fill="var(--accent-strong)">
            <animate attributeName="opacity" values="0.5;1;0.5"
                     dur={`${1.5 + (n.id % 5) * 0.4}s`}
                     begin={`${(n.id * 0.07) % 2}s`}
                     repeatCount="indefinite" />
          </circle>
        ))}
      </g>

      {/* central core */}
      <circle cx="160" cy="160" r="48" fill="url(#nc-core)" opacity={busy ? 1 : 0.85}>
        {busy ? <animate attributeName="opacity" values="0.75;1;0.75" dur="1.4s" repeatCount="indefinite" /> : null}
      </circle>
      <circle cx="160" cy="160" r="18" fill="var(--accent-strong)" opacity="0.22" />
      <circle cx="160" cy="160" r="6" fill="var(--accent-strong)" filter="url(#nc-glow)">
        <animate attributeName="r" values="5;8;5" dur="2.4s" repeatCount="indefinite" />
      </circle>

      {/* spinning thin ring near core */}
      <g style={{ transformOrigin: "160px 160px", animation: "rotate-cw 5s linear infinite" }}>
        <circle cx="160" cy="160" r="30" fill="none" stroke="url(#nc-sweep)" strokeWidth="1.2" />
      </g>

      {/* corner brackets w/ readouts */}
      {[
        { x: 38,  y: 38,  d: "M 0 12 L 0 0 L 12 0", label: "NEURAL", val: "ACTIVE" },
        { x: 282, y: 38,  d: "M -12 0 L 0 0 L 0 12", label: "SYNAPSE", val: "1.24M" },
        { x: 38,  y: 282, d: "M 0 -12 L 0 0 L 12 0", label: "COHERE", val: "98.4%" },
        { x: 282, y: 282, d: "M -12 0 L 0 0 L 0 -12", label: "MEMORY", val: "312N" },
      ].map((c, i) => (
        <g key={i} transform={`translate(${c.x},${c.y})`}>
          <path d={c.d} stroke="var(--accent-strong)" strokeWidth="1.2" fill="none" opacity="0.85" />
          <text x={c.x < 160 ? 6 : -6} y={c.y < 160 ? 14 : -6}
                textAnchor={c.x < 160 ? "start" : "end"}
                fontFamily="JetBrains Mono, monospace" fontSize="5.5"
                fill="var(--accent-text)" opacity="0.7" letterSpacing="1.2">{c.label}</text>
          <text x={c.x < 160 ? 6 : -6} y={c.y < 160 ? 22 : -14}
                textAnchor={c.x < 160 ? "start" : "end"}
                fontFamily="JetBrains Mono, monospace" fontSize="7"
                fill="var(--ink)" letterSpacing="1">{c.val}</text>
        </g>
      ))}

      {/* drifting particles */}
      <g opacity="0.65">
        {Array.from({ length: 14 }).map((_, i) => {
          const a = (i / 14) * Math.PI * 2;
          const r1 = 130 + (i % 3) * 8;
          const r2 = 165 + (i % 4) * 6;
          const x1 = 160 + Math.cos(a) * r1, y1 = 160 + Math.sin(a) * r1;
          const x2 = 160 + Math.cos(a) * r2, y2 = 160 + Math.sin(a) * r2;
          const dur = 3 + (i % 4) * 1.3;
          return (
            <circle key={i} r="0.9" fill="var(--accent-strong)">
              <animate attributeName="cx" values={`${x1};${x2};${x1}`} dur={`${dur}s`} repeatCount="indefinite" />
              <animate attributeName="cy" values={`${y1};${y2};${y1}`} dur={`${dur}s`} repeatCount="indefinite" />
              <animate attributeName="opacity" values="0;0.9;0" dur={`${dur}s`} repeatCount="indefinite" />
            </circle>
          );
        })}
      </g>
    </svg>
  );
}

/* keyframe injection for SVG rotations */
const kfStyle = document.createElement("style");
kfStyle.textContent = `
@keyframes rotate-cw  { from { transform: rotate(0); } to { transform: rotate(360deg); } }
@keyframes rotate-ccw { from { transform: rotate(0); } to { transform: rotate(-360deg); } }
@keyframes hex-pulse  { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }
`;
document.head.appendChild(kfStyle);

/* ── Top status rail ──────────────────────────────────────── */
function StatusRail({ mode, latency, uptime, model, sessionId }) {
  return (
    <div className="rail">
      <div className="brand">
        <div className="brand-mark"></div>
        <span>VERONICA · OS</span>
      </div>
      <div className="segment"><span className="seg-key">MODE</span><span className="seg-val" style={{ color: "var(--accent-text)" }}>{mode.label}</span></div>
      <div className="segment"><span className="seg-key">MODEL</span><span className="seg-val">{model}</span></div>
      <div className="segment"><span className="seg-key">SESSION</span><span className="seg-val">{sessionId}</span></div>
      <div className="segment"><span className="seg-key">UPTIME</span><span className="seg-val">{uptime}</span></div>
      <div className="segment"><span className="seg-key">LATENCY</span><span className="seg-val">{latency}ms</span></div>
      <div className="spacer"></div>
      <div className="status-pill"><span className="dot"></span> REACTOR ONLINE</div>
    </div>
  );
}

/* ── Mode selector ────────────────────────────────────────── */
function ModeSelector({ mode, setMode }) {
  return (
    <div className="hud">
      <div className="section-head">
        <span className="title">◇ Cognitive Mode</span>
        <span className="meta">4 / 4</span>
      </div>
      <div className="section-body">
        <div className="mode-list">
          {MODES.map((m) => (
            <button
              key={m.id}
              className={`mode-btn ${mode.id === m.id ? "active" : ""}`}
              onClick={() => setMode(m)}
              aria-pressed={mode.id === m.id}
            >
              <span className="mode-glyph">{m.glyph}</span>
              <span>
                <span className="mode-name" style={{ color: mode.id === m.id ? "var(--accent-text)" : undefined }}>{m.label}</span>
                <div className="mode-sub">{m.sub}</div>
              </span>
              <span className="mono mode-key">{m.key}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Telemetry panel ──────────────────────────────────────── */
function useSparkline(maxLen = 20, base = 40, jitter = 18) {
  const [data, setData] = useState(() => Array.from({ length: maxLen }, () => base + Math.random() * jitter));
  useEffect(() => {
    const iv = setInterval(() => {
      setData((prev) => {
        const last = prev[prev.length - 1];
        const next = Math.max(8, Math.min(96, last + (Math.random() - 0.5) * 14));
        return [...prev.slice(1), next];
      });
    }, 1200);
    return () => clearInterval(iv);
  }, []);
  return data;
}

function Bar({ value, label, sub, scale }) {
  const cls = value > 85 ? "crit" : value > 65 ? "warn" : "";
  return (
    <div className="tele-row">
      <div className="top">
        <span className="k">{label}</span>
        <span className="v">{Math.round(value)}{sub}</span>
      </div>
      <div className="bar"><div className={`bar-fill ${cls}`} style={{ width: `${Math.min(value, 100)}%` }}></div></div>
      {scale ? <div className="scale">{scale}</div> : null}
    </div>
  );
}

function TelemetryPanel() {
  const cpu = useSparkline(24, 32, 20);
  const ram = useSparkline(24, 60, 10);
  const tok = useSparkline(20, 50, 30);

  const cpuNow = cpu[cpu.length - 1];
  const ramNow = ram[ram.length - 1];
  const tokNow = tok[tok.length - 1];

  return (
    <div className="hud">
      <div className="section-head">
        <span className="title">◈ Telemetry</span>
        <span className="meta">live · 1s</span>
      </div>
      <div className="section-body">
        <div className="tele-grid">
          <Bar value={cpuNow} label="CPU" sub="%" scale="QWEN2.5:7B · 4-bit Q" />
          <Bar value={ramNow} label="RAM" sub="%" scale="9.4 / 16.0 GB" />
          <div className="tele-row full-row">
            <div className="top">
              <span className="k">Tokens / sec</span>
              <span className="v">{Math.round(tokNow)}<span style={{ color: "var(--ink-ghost)", marginLeft: 4 }}>t/s</span></span>
            </div>
            <div className="spark">
              {tok.map((v, i) => <div key={i} className="bar-tick" style={{ height: `${v}%` }}></div>)}
            </div>
          </div>
          <div className="tele-row full-row">
            <div className="top">
              <span className="k">Disk · veronica.db</span>
              <span className="v">142 / 256 GB</span>
            </div>
            <div className="bar"><div className="bar-fill" style={{ width: "55%" }}></div></div>
            <div className="scale">embeds: 1,408 · memories: 312 · life-log: 4,790</div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Live readout hook ─────────────────────────────────── */
function useDrift(start, jitter = 1, every = 1500, fixed = 1) {
  const [v, setV] = useState(start);
  useEffect(() => {
    const iv = setInterval(() => {
      setV((cur) => {
        const next = cur + (Math.random() - 0.5) * jitter * 2;
        return Number(next.toFixed(fixed));
      });
    }, every);
    return () => clearInterval(iv);
  }, [jitter, every, fixed]);
  return v;
}

function useCounter(start, every = 900, max = 9.9e9) {
  const [v, setV] = useState(start);
  useEffect(() => {
    const iv = setInterval(() => setV((c) => Math.min(max, c + Math.floor(1 + Math.random() * 80))), every);
    return () => clearInterval(iv);
  }, [every, max]);
  return v;
}

function formatBig(n) {
  if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(n);
}

/* ── Reactor card ─────────────────────────────────────────── */
function ReactorCard({ mode, busy, isListening }) {
  const hz       = useDrift(92.4, 1.8, 900,  1);
  const syn      = useCounter(1_241_882, 700);
  const coh      = useDrift(98.4, 0.12, 1300, 2);
  const proc     = useDrift(4.7,  0.4,  900,  1);
  const drift    = useDrift(0.012, 0.004, 1700, 3);
  const ctx      = useDrift(7.8,  0.18, 2100, 1);
  const ingest   = useCounter(1_408_211, 320);
  const protocols = 14;

  const leftStats = [
    { k: "NEURAL ACTIVITY", v: `${hz} Hz`,           bar: Math.min(100, hz) },
    { k: "SYNAPSES",         v: formatBig(syn) },
    { k: "PROTOCOLS ACTIVE", v: `${protocols} / 56` },
    { k: "MEMORY DEPTH",     v: "312 nodes" },
  ];
  const rightStats = [
    { k: "COHERENCE",   v: `${coh}%`,    bar: coh, accent: true },
    { k: "CONFIDENCE",  v: "HIGH",       accent: true },
    { k: "PROCESSING",  v: `${proc} ms` },
    { k: "DRIFT",       v: `${drift}σ` },
  ];

  return (
    <div className="hud reactor-hud">
      <div className="section-head">
        <span className="title">◉ Neural Core · {mode.label}</span>
        <span className="meta">{isListening ? "voice in" : busy ? "thinking…" : "armed · nominal"}</span>
      </div>

      <div className="neural-wrap">
        <div className="neural-stat-col left">
          {leftStats.map((s, i) => (
            <div key={i} className="neural-stat">
              <div className="k">{s.k}</div>
              <div className={`v ${s.accent ? "accent" : ""}`}>{s.v}</div>
              {s.bar != null ? <div className="mini-bar"><div className="mini-bar-fill" style={{ width: `${Math.min(100, s.bar)}%` }}></div></div> : null}
            </div>
          ))}
        </div>

        <div className="neural-core-wrap">
          <NeuralCore busy={busy} />
          <div className="neural-overlay-label top mono">VRC · NEURAL CORE · v0.7.3</div>
          <div className="neural-overlay-label bottom mono">{mode.label}-DOCTRINE · ARMED</div>
        </div>

        <div className="neural-stat-col right">
          {rightStats.map((s, i) => (
            <div key={i} className="neural-stat right">
              <div className="k">{s.k}</div>
              <div className={`v ${s.accent ? "accent" : ""}`}>{s.v}</div>
              {s.bar != null ? <div className="mini-bar"><div className="mini-bar-fill" style={{ width: `${Math.min(100, s.bar)}%` }}></div></div> : null}
            </div>
          ))}
        </div>
      </div>

      <div className="neural-strip mono">
        <div className="strip-cell"><span className="k">INGEST</span><span className="v">{formatBig(ingest)} tok/s</span></div>
        <div className="strip-cell"><span className="k">CONTEXT</span><span className="v">{ctx} / 32K</span></div>
        <div className="strip-cell"><span className="k">SAFETY</span><span className="v">2 PEND · 14 PASS</span></div>
        <div className="strip-cell"><span className="k">REACTOR</span><span className="v ok">● ONLINE</span></div>
        <div className="strip-cell"><span className="k">UTC</span><span className="v">17:42:08</span></div>
      </div>

      <div className="reactor-foot">
        <span className="mode-pill"><span className="dot"></span>{mode.label}</span>
        <span className="brief">{mode.briefing}</span>
        <span className="mono" style={{ color: "var(--ink-ghost)", fontSize: 10, letterSpacing: "0.18em" }}>FLT · NOMINAL</span>
      </div>
    </div>
  );
}

/* ── Chat ─────────────────────────────────────────────────── */
const SEED_MESSAGES = [
  { role: "veronica", text: "Sir, VERONICA is online. Command center initialized, modes armed, voice pipeline standing by. Subtle, tasteful, mildly overqualified." },
  { role: "system",   text: "─── 17:36 · session restored · 312 memories indexed ───" },
  { role: "commander",text: "Brief me. What's on deck today?" },
  { role: "veronica", text: "Three priorities: design review with Maya at 14:00, the SENTINEL upgrade you flagged Tuesday, and an unread thread from Yusuf marked important. Two reminders fire before noon. Calendar is otherwise clear until 16:30.",
    tool: { name: "calendar.list_today", lat: 142, ok: true } },
  { role: "commander",text: "Draft a reply to Yusuf — I'll review before send." },
];

function Chat({ mode, busy, onSend, streamingText }) {
  const [msgs, setMsgs] = useState(SEED_MESSAGES);
  const feedRef = useRef(null);

  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [msgs, streamingText]);

  useEffect(() => {
    // expose appender to parent via window for the command bar
    window.__veronica_append = (role, text, tool) => setMsgs((m) => [...m, { role, text, tool }]);
  }, []);

  return (
    <div className="hud chat">
      <div className="section-head">
        <span className="title">▤ Conversational Stream</span>
        <span className="meta">{busy ? "streaming…" : "ready"}</span>
      </div>
      <div className="chat-feed" ref={feedRef}>
        {msgs.map((m, i) => {
          if (m.role === "system") return <div key={i} className="bubble system">{m.text}</div>;
          return (
            <div key={i} className={`bubble ${m.role}`}>
              <div className="who">{m.role === "veronica" ? "VERONICA" : "COMMANDER"}</div>
              <div>{m.text}</div>
              {m.tool ? (
                <div className="tool-line">
                  <span className="ok">●</span> tool · <span style={{ color: "var(--ink)" }}>{m.tool.name}</span> · {m.tool.lat}ms · {m.tool.ok ? "ok" : "fail"}
                </div>
              ) : null}
            </div>
          );
        })}
        {streamingText ? (
          <div className="bubble veronica">
            <div className="who">VERONICA</div>
            <div>{streamingText}<span className="cursor"></span></div>
          </div>
        ) : null}
      </div>
      <div className="divlabel">Suggested protocols</div>
      <div className="chip-row">
        <button className="chip" onClick={() => onSend("Draft reply to Yusuf, professional, ~80 words.")}><span className="glyph">›_</span>Draft Yusuf reply</button>
        <button className="chip" onClick={() => onSend("Summarize my inbox.")}><span className="glyph">›_</span>Triage inbox</button>
        <button className="chip" onClick={() => onSend("Start a 25-minute focus session.")}><span className="glyph">›_</span>Focus 25</button>
        <button className="chip" onClick={() => onSend("Run security review on the last 24h.")}><span className="glyph">›_</span>Sentinel sweep</button>
      </div>
      <CommandBar busy={busy} onSend={onSend} mode={mode} />
    </div>
  );
}

function CommandBar({ busy, onSend, mode }) {
  const [val, setVal] = useState("");
  const submit = (e) => {
    e.preventDefault();
    if (!val.trim() || busy) return;
    onSend(val);
    setVal("");
  };
  return (
    <form className="command-bar" onSubmit={submit}>
      <div className="prompt mono">›_</div>
      <input
        value={val}
        onChange={(e) => setVal(e.target.value)}
        placeholder={`Veronica, deploy ${mode.label.toLowerCase()} protocol…`}
        autoComplete="off"
      />
      <button type="button" className="mic" aria-label="Voice input" title="Voice">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2"/><path d="M12 19v3"/></svg>
      </button>
      <button type="submit" className="send" disabled={busy || !val.trim()}>Transmit</button>
    </form>
  );
}

/* ── Briefing ─────────────────────────────────────────────── */
function Briefing({ mode }) {
  return (
    <div className="hud">
      <div className="section-head">
        <span className="title">▤ Daily Briefing</span>
        <span className="meta">17:42 · tuesday</span>
      </div>
      <div className="brief-card">
        <div className="corner">B</div>
        <div className="text">
          <strong>Three priorities surfaced.</strong> Calendar shows a clean afternoon until your 14:00 with Maya. Inbox contains one important thread from <strong>Yusuf</strong> awaiting response — last touched 09:14. The <strong>SENTINEL audit</strong> flagged Tuesday is still pending; suggest queueing tonight after the focus block.
        </div>
      </div>
    </div>
  );
}

/* ── Protocols / Tasks / Inbox panels ─────────────────────── */
function ProtocolsPanel({ onSend }) {
  const items = [
    { ico: "M", t: "Morning briefing",    s: "calendar · tasks · inbox",  badge: "⌘B" },
    { ico: "F", t: "25-min focus block",  s: "pomodoro · DnD · lo-fi",    badge: "⌘F" },
    { ico: "T", t: "Inbox triage",        s: "label · draft · queue",     badge: "⌘T" },
    { ico: "R", t: "Risk review",         s: "sentinel · last 24h",       badge: "⌘R" },
    { ico: "J", t: "Journal end-of-day",  s: "life-log · summary",        badge: "⌘J" },
  ];
  return (
    <div className="hud">
      <div className="section-head">
        <span className="title">◇ Protocols</span>
        <span className="meta">5 ready</span>
      </div>
      <div className="section-body">
        <div className="list">
          {items.map((it) => (
            <div key={it.t} className="list-item" onClick={() => onSend(`Run ${it.t.toLowerCase()}.`)}>
              <div className="ico mono">{it.ico}</div>
              <div className="desc"><span className="t">{it.t}</span><span className="s">{it.s}</span></div>
              <div className="badge mono">{it.badge}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function AlertsPanel() {
  const items = [
    { kind: "warn", ico: "!", t: "Yusuf · awaiting reply",      s: "important · 8h ago" },
    { kind: "",     ico: "✓", t: "Backup completed",            s: "veronica.db · 142 MB" },
    { kind: "crit", ico: "▲", t: "Confirm: send email to Maya", s: "draft ready · gmail.send" },
    { kind: "",     ico: "✓", t: "Memory backfill: 312 → 408",  s: "nomic-embed-text" },
    { kind: "",     ico: "⌁", t: "Spotify · focus playlist",    s: "lo-fi · auto-armed"},
  ];
  return (
    <div className="hud">
      <div className="section-head">
        <span className="title">◬ Notifications</span>
        <span className="meta">5 · 1 pending</span>
      </div>
      <div className="section-body">
        <div className="list">
          {items.map((it, i) => (
            <div key={i} className={`list-item ${it.kind === "warn" ? "alert-warn" : it.kind === "crit" ? "alert-crit" : ""}`}>
              <div className="ico mono">{it.ico}</div>
              <div className="desc"><span className="t">{it.t}</span><span className="s">{it.s}</span></div>
              <div className="badge mono">{i < 2 ? "NEW" : ""}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SecurityRules({ mode }) {
  const [rules, setRules] = useState({
    confirm: true,
    secrets: true,
    audit: true,
    shell: true,
    autoreply: false,
  });
  const toggle = (k) => setRules((r) => ({ ...r, [k]: !r[k] }));
  const row = (k, label) => (
    <div className="rule-row" onClick={() => toggle(k)} style={{ cursor: "pointer" }}>
      <span>{label}</span>
      <span className={`pill ${rules[k] ? "" : "off"}`}>{rules[k] ? "ON" : "OFF"}</span>
    </div>
  );
  return (
    <div className="hud">
      <div className="section-head">
        <span className="title">⊕ Security Doctrine</span>
        <span className="meta">{mode.label === "SENTINEL" ? "elevated" : "baseline"}</span>
      </div>
      <div className="section-body">
        {row("confirm",  "Dangerous actions require confirmation")}
        {row("secrets",  "Secrets stay server-side")}
        {row("audit",    "Autonomous steps are logged")}
        {row("shell",    "Shell execution is whitelist-first")}
        {row("autoreply","Auto-reply to known senders")}
      </div>
    </div>
  );
}

function ActivityPanel() {
  const events = [
    { t: "17:41", tag: "MEM",  text: "Indexed note · \"reactor v3 spec\"" },
    { t: "17:36", tag: "MAIL", text: "Drafted reply to maya@…" },
    { t: "17:21", tag: "CAL",  text: "Scheduled focus block 18:00" },
    { t: "17:14", tag: "RUN",  text: "Tool ran · web.search · 188ms" },
    { t: "16:55", tag: "SEC",  tagKind: "warn", text: "Sentinel · suspicious login flagged" },
    { t: "16:32", tag: "GH",   text: "Imported issue #142 → tasks" },
  ];
  return (
    <div className="hud">
      <div className="section-head">
        <span className="title">▤ Life Log</span>
        <span className="meta">live</span>
      </div>
      <div className="section-body">
        <div className="activity">
          {events.map((e, i) => (
            <div key={i} className="row">
              <span className="t mono">{e.t}</span>
              <span className="what"><span className={`tag mono ${e.tagKind === "warn" ? "warn" : ""}`}>{e.tag}</span>{e.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── App ──────────────────────────────────────────────────── */
function App() {
  const [mode, setMode] = useState(MODES[0]);
  const [busy, setBusy] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [latency, setLatency] = useState(142);
  const [uptime, setUptime] = useState(0);
  const startedAt = useRef(Date.now() - 1000 * 60 * 47);

  // tweaks
  const TWEAK_DEFAULS = /*EDITMODE-BEGIN*/{
    "mode": "jarvis",
    "showScanlines": true,
    "showSweep": true,
    "layout": "command",
    "density": "comfortable"
  }/*EDITMODE-END*/;
  const [tweaks, setTweak] = window.useTweaks
    ? window.useTweaks(TWEAK_DEFAULS)
    : [TWEAK_DEFAULS, () => {}];

  // sync mode → tweak
  useEffect(() => {
    const m = MODES.find((mm) => mm.id === tweaks.mode);
    if (m && m.id !== mode.id) setMode(m);
  }, [tweaks.mode]);

  useEffect(() => {
    document.documentElement.setAttribute("data-mode", mode.id);
  }, [mode]);

  // uptime ticker
  useEffect(() => {
    const iv = setInterval(() => setUptime(Math.floor((Date.now() - startedAt.current) / 1000)), 1000);
    return () => clearInterval(iv);
  }, []);

  // wobble latency
  useEffect(() => {
    const iv = setInterval(() => setLatency((l) => Math.max(80, Math.min(260, l + Math.round((Math.random() - 0.5) * 40)))), 1800);
    return () => clearInterval(iv);
  }, []);

  // keyboard: ⌥1..4
  useEffect(() => {
    const fn = (e) => {
      if (!e.altKey) return;
      const idx = ["1","2","3","4"].indexOf(e.key);
      if (idx >= 0) {
        const m = MODES[idx];
        setMode(m);
        setTweak("mode", m.id);
      }
    };
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, []);

  const formatUptime = (s) => {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
  };

  const onSend = useCallback((text) => {
    if (busy || !text.trim()) return;
    window.__veronica_append && window.__veronica_append("commander", text);
    setBusy(true);
    setStreamingText("");

    const replies = {
      jarvis: "Acknowledged. I have routed this through the general planner. Three steps queued; first is non-destructive and will run immediately. The remaining two require your sign-off.",
      friday: "On it. I will set a 25-minute focus block, queue the reply for review, and silence non-critical notifications until the timer ends.",
      veronica: "Risk-ranked the request. Two viable paths. I recommend path A — lower blast radius, faster recovery — pending your go.",
      sentinel: "Audit started. Scanning permissions, tokens and outbound calls for the last 24h. Two items already flagged for review.",
    };
    const full = replies[mode.id];
    let i = 0;
    const iv = setInterval(() => {
      i += Math.max(1, Math.floor(Math.random() * 4));
      const chunk = full.slice(0, i);
      setStreamingText(chunk);
      if (i >= full.length) {
        clearInterval(iv);
        setTimeout(() => {
          window.__veronica_append && window.__veronica_append("veronica", full, { name: "agent.respond", lat: 124 + Math.round(Math.random()*60), ok: true });
          setStreamingText("");
          setBusy(false);
        }, 200);
      }
    }, 35);
  }, [busy, mode]);

  const sessionId = useMemo(() => "0xA7F2-1480", []);

  return (
    <>
      {tweaks.showScanlines ? <div className="scanlines"></div> : null}
      {tweaks.showSweep ? <div className="scan-sweep"></div> : null}

      <StatusRail
        mode={mode}
        latency={latency}
        uptime={formatUptime(uptime)}
        model="qwen2.5:7b"
        sessionId={sessionId}
      />

      <div className="shell with-tools">
        <div className="col left">
          <ModeSelector mode={mode} setMode={(m) => { setMode(m); setTweak("mode", m.id); }} />
          <TelemetryPanel />
          <SecurityRules mode={mode} />
        </div>

        <div className="col center">
          <ReactorCard mode={mode} busy={busy} isListening={false} />
          <Briefing mode={mode} />
          <Chat mode={mode} busy={busy} onSend={onSend} streamingText={streamingText} />
        </div>

        <div className="col right">
          <ProtocolsPanel onSend={onSend} />
          <AlertsPanel />
          <ActivityPanel />
        </div>

        <div className="tools-wrap">
          {window.ToolSurfaces ? <window.ToolSurfaces onSend={onSend} mode={mode} /> : null}
        </div>
      </div>

      <div className="footer-rail">
        <div className="group">
          <span><span className="ok">●</span> api · localhost:8000</span>
          <span><span className="ok">●</span> ollama · 11434</span>
          <span><span className="ok">●</span> whisper · armed</span>
          <span><span className="ok">●</span> gmail · authorised</span>
        </div>
        <div className="group">
          <span>build · v0.7.3-arc</span>
          <span>©2026 VERONICA</span>
        </div>
      </div>

      {/* Tweaks panel */}
      {window.TweaksPanel ? (
        <window.TweaksPanel title="Tweaks">
          <window.TweakSection label="Mode">
            <window.TweakSelect label="Cognitive mode" value={tweaks.mode} onChange={(v) => setTweak("mode", v)} options={[
              { value: "jarvis",   label: "JARVIS · cyan" },
              { value: "friday",   label: "FRIDAY · gold" },
              { value: "veronica", label: "VERONICA · violet" },
              { value: "sentinel", label: "SENTINEL · red" },
            ]} />
          </window.TweakSection>
          <window.TweakSection label="Ambient FX">
            <window.TweakToggle label="Scanlines" value={tweaks.showScanlines} onChange={(v) => setTweak("showScanlines", v)} />
            <window.TweakToggle label="Scan sweep" value={tweaks.showSweep} onChange={(v) => setTweak("showSweep", v)} />
          </window.TweakSection>
          <window.TweakSection label="Demo">
            <window.TweakButton label="Send sample command" onClick={() => onSend("Run a status check.")} />
          </window.TweakSection>
        </window.TweaksPanel>
      ) : null}
    </>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);





/* Tools surface — surfaces every backend tool as a tabbed panel */
const { useState: _useState, useMemo: _useMemo } = React;

const TOOL_TABS = [
  { id: "mail",      label: "Mail",       glyph: "✉", short: "MAIL" },
  { id: "calendar",  label: "Calendar",   glyph: "▦", short: "CAL" },
  { id: "whatsapp",  label: "WhatsApp",   glyph: "◌", short: "WA" },
  { id: "github",    label: "GitHub",     glyph: "❮❯", short: "GH" },
  { id: "spotify",   label: "Spotify",    glyph: "♪", short: "SPT" },
  { id: "habits",    label: "Habits",     glyph: "✓", short: "HBT" },
  { id: "news",      label: "News",       glyph: "▤", short: "NWS" },
  { id: "ops",       label: "Operations", glyph: "◇", short: "OPS" },
  { id: "clipboard", label: "Clipboard",  glyph: "⊟", short: "CLP" },
  { id: "pomodoro",  label: "Pomodoro",   glyph: "◐", short: "POM" },
  { id: "search",    label: "Web",        glyph: "◎", short: "WEB" },
  { id: "planner",   label: "Planner",    glyph: "❖", short: "PLN" },
];

/* ── Generic atoms ──────────────────────────────────────── */
function ToolHeader({ title, sub, action }) {
  return (
    <div className="tool-header">
      <div>
        <div className="tool-title">{title}</div>
        {sub ? <div className="tool-sub">{sub}</div> : null}
      </div>
      {action}
    </div>
  );
}

function Row({ left, right, sub, status, onClick }) {
  return (
    <div className={`tool-row ${onClick ? "clickable" : ""}`} onClick={onClick}>
      <div className="tool-row-main">
        <div className="tool-row-left">{left}</div>
        {sub ? <div className="tool-row-sub">{sub}</div> : null}
      </div>
      <div className="tool-row-right">
        {status ? <span className={`tool-pill ${status.kind || ""}`}>{status.text}</span> : null}
        {right ? <span className="tool-row-meta mono">{right}</span> : null}
      </div>
    </div>
  );
}

function Empty({ children }) {
  return <div className="tool-empty">{children}</div>;
}

/* ── MAIL ───────────────────────────────────────────────── */
function MailView({ onSend }) {
  const inbox = [
    { from: "Yusuf Ahmed",     subject: "Re: Reactor v3 spec",       snippet: "I've got two questions on the core safeties — section 4.2 specifically…", time: "09:14", unread: true,  important: true  },
    { from: "Maya Iyer",       subject: "Design review — 14:00",      snippet: "Meeting room is booked. Bringing the printed wireframes too.",         time: "08:42", unread: true,  important: false },
    { from: "Stripe",          subject: "Receipt · invoice #4218",    snippet: "Thank you for your payment of $129.00 — please find your receipt…",   time: "07:30", unread: false, important: false },
    { from: "GitHub",          subject: "PR #142 ready for review",   snippet: "Beastburner opened a pull request: \"feat: semantic memory backfill…\"", time: "06:55", unread: false, important: false },
    { from: "Linear",          subject: "8 issues moved to In Review", snippet: "Your team moved 8 issues into review since you last visited.",       time: "Yest", unread: false, important: false },
  ];
  return (
    <>
      <ToolHeader
        title="Gmail · Inbox"
        sub={`${inbox.filter(i => i.unread).length} unread · ${inbox.length} loaded · gmail_inbox`}
        action={<button className="tool-action" onClick={() => onSend("Triage my inbox.")}>Triage</button>}
      />
      <div className="tool-list">
        {inbox.map((m, i) => (
          <Row
            key={i}
            left={
              <>
                <span className={`mail-dot ${m.unread ? "unread" : ""} ${m.important ? "imp" : ""}`}></span>
                <span className="mail-from">{m.from}</span>
                <span className="mail-subject">{m.subject}</span>
              </>
            }
            sub={m.snippet}
            right={m.time}
            status={m.important ? { text: "IMP", kind: "warn" } : null}
            onClick={() => onSend(`Open email from ${m.from}: ${m.subject}.`)}
          />
        ))}
      </div>
      <div className="tool-compose">
        <div className="compose-grid">
          <input className="tool-input" placeholder="to · maya@…" />
          <input className="tool-input" placeholder="subject" />
        </div>
        <textarea className="tool-textarea" placeholder="Draft body — Veronica will edit & confirm before send." rows={3}></textarea>
        <div className="tool-actions">
          <button className="tool-btn ghost" onClick={() => onSend("Draft a reply to Yusuf.")}>Draft</button>
          <button className="tool-btn">Save as draft</button>
          <button className="tool-btn danger" onClick={() => onSend("Send the draft after I confirm.")}>Send · requires confirm</button>
        </div>
      </div>
    </>
  );
}

/* ── CALENDAR ───────────────────────────────────────────── */
function CalendarView({ onSend }) {
  const events = [
    { time: "09:00", end: "09:30", title: "Stand-up · Core team",    where: "Meet · jdr-xyz", who: "5 attendees", color: "accent" },
    { time: "11:00", end: "12:00", title: "1:1 · Aarav",              where: "Office · 4A",    who: "Aarav S.",     color: "" },
    { time: "14:00", end: "15:00", title: "Design review · Maya",     where: "Studio",         who: "Maya, Eun-Ji",  color: "accent", focus: true },
    { time: "16:30", end: "17:00", title: "SENTINEL audit prep",      where: "Solo",           who: "Veronica",      color: "warn" },
    { time: "19:00", end: "19:25", title: "Focus block (deep work)",  where: "Pomodoro",       who: "Solo",          color: "" },
  ];
  return (
    <>
      <ToolHeader
        title="Calendar · Today"
        sub="Tue · 13 May · 5 events · calendar_events"
        action={<button className="tool-action" onClick={() => onSend("Find a free slot tomorrow for 60 minutes.")}>Find slot</button>}
      />
      <div className="cal-grid">
        <div className="cal-timeline">
          {Array.from({ length: 13 }).map((_, i) => {
            const h = 8 + i;
            return <div key={i} className="cal-hour"><span className="mono">{String(h).padStart(2,"0")}:00</span></div>;
          })}
          {events.map((e, i) => {
            const startH = parseInt(e.time.split(":")[0]) + parseInt(e.time.split(":")[1])/60;
            const endH = parseInt(e.end.split(":")[0]) + parseInt(e.end.split(":")[1])/60;
            const top = (startH - 8) * 40;
            const h = Math.max(28, (endH - startH) * 40);
            return (
              <div key={i} className={`cal-event ${e.color} ${e.focus ? "focus" : ""}`} style={{ top, height: h }}>
                <div className="cal-evt-time mono">{e.time}–{e.end}</div>
                <div className="cal-evt-title">{e.title}</div>
                <div className="cal-evt-sub">{e.where} · {e.who}</div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="tool-compose">
        <div className="compose-grid three">
          <input className="tool-input" placeholder="title" defaultValue="Sync with Yusuf" />
          <input className="tool-input mono" placeholder="start" defaultValue="2026-05-14 15:00" />
          <input className="tool-input mono" placeholder="end"   defaultValue="2026-05-14 15:30" />
        </div>
        <div className="tool-actions">
          <button className="tool-btn ghost" onClick={() => onSend("Find free 60min tomorrow.")}>Free slots</button>
          <button className="tool-btn danger" onClick={() => onSend("Schedule sync with Yusuf tomorrow 3pm.")}>Schedule · requires confirm</button>
        </div>
      </div>
    </>
  );
}

/* ── WHATSAPP ───────────────────────────────────────────── */
function WhatsAppView({ onSend }) {
  const threads = [
    { name: "Maya I.",        last: "Sounds good — 14:00 works.",         unread: 2, time: "08:42", online: true  },
    { name: "Family",         last: "Mom: dinner sunday?",                unread: 5, time: "08:10", online: false },
    { name: "Dev group",      last: "Aarav: deployed to staging ✓",       unread: 0, time: "Yest", online: true  },
    { name: "Yusuf A.",       last: "okay sending the spec now",          unread: 0, time: "Yest", online: false },
    { name: "Sneha (Doctor)", last: "Reminder: appointment Friday 11am",  unread: 1, time: "Mon",  online: false },
  ];
  return (
    <>
      <ToolHeader
        title="WhatsApp · Bridge"
        sub="paired · 5 contacts · whatsapp_messages"
        action={<span className="status-pill ok">● bridge online</span>}
      />
      <div className="tool-list">
        {threads.map((t, i) => (
          <Row
            key={i}
            left={
              <>
                <span className={`avatar ${t.online ? "online" : ""}`}>{t.name.split(" ").map(s => s[0]).slice(0,2).join("")}</span>
                <span className="mail-from">{t.name}</span>
              </>
            }
            sub={t.last}
            right={t.time}
            status={t.unread > 0 ? { text: String(t.unread), kind: "count" } : null}
            onClick={() => onSend(`Summarize my WhatsApp thread with ${t.name}.`)}
          />
        ))}
      </div>
      <div className="tool-compose">
        <div className="compose-grid">
          <input className="tool-input" placeholder="to · contact name" />
          <input className="tool-input" placeholder="message preview" />
        </div>
        <div className="tool-actions">
          <button className="tool-btn ghost" onClick={() => onSend("Summarize my WhatsApp messages.")}>Summarize all</button>
          <button className="tool-btn danger" onClick={() => onSend("Draft a WhatsApp reply to Maya.")}>Send · requires confirm</button>
        </div>
      </div>
    </>
  );
}

/* ── GITHUB ─────────────────────────────────────────────── */
function GitHubView({ onSend }) {
  const issues = [
    { num: 142, title: "feat: semantic memory backfill",       state: "open",  labels: ["enhancement"], age: "2d" },
    { num: 139, title: "bug: pomodoro status stale after stop", state: "open",  labels: ["bug"],         age: "5d" },
    { num: 137, title: "docs: clarify Ollama setup on macOS",   state: "open",  labels: ["docs"],        age: "1w" },
  ];
  const prs = [
    { num: 41, title: "feat: tabbed tool surfaces",        author: "you",   age: "2h", checks: "3/3" },
    { num: 39, title: "refactor: storage helpers",         author: "aarav", age: "1d", checks: "2/3" },
  ];
  return (
    <>
      <ToolHeader
        title="GitHub · Beastburner/Veronica"
        sub="main · 1,408 commits · github_list_prs"
        action={<button className="tool-action" onClick={() => onSend("Create a GitHub issue from this conversation.")}>New issue</button>}
      />
      <div className="gh-stats">
        <div className="gh-stat"><div className="k">⭐ Stars</div><div className="v mono">182</div></div>
        <div className="gh-stat"><div className="k">⑂ Forks</div><div className="v mono">14</div></div>
        <div className="gh-stat"><div className="k">◯ Open</div><div className="v mono">3</div></div>
        <div className="gh-stat"><div className="k">↗ PRs</div><div className="v mono">2</div></div>
      </div>
      <div className="divlabel-sm">Pull requests</div>
      <div className="tool-list">
        {prs.map((p) => (
          <Row
            key={p.num}
            left={<><span className="gh-tag">#{p.num}</span><span className="mail-from">{p.title}</span></>}
            sub={`by ${p.author} · ${p.age} · checks ${p.checks}`}
            status={{ text: "REVIEW", kind: "warn" }}
            onClick={() => onSend(`Review PR #${p.num}.`)}
          />
        ))}
      </div>
      <div className="divlabel-sm">Open issues</div>
      <div className="tool-list">
        {issues.map((it) => (
          <Row
            key={it.num}
            left={<><span className="gh-tag">#{it.num}</span><span className="mail-from">{it.title}</span></>}
            sub={`labels: ${it.labels.join(", ")} · opened ${it.age}`}
            right={it.age}
            onClick={() => onSend(`Triage issue #${it.num}.`)}
          />
        ))}
      </div>
    </>
  );
}

/* ── SPOTIFY ────────────────────────────────────────────── */
function SpotifyView({ onSend, mode }) {
  const [playing, setPlaying] = _useState(true);
  const modePlaylists = {
    jarvis:   { name: "Deep Focus · Strings",  count: 84 },
    friday:   { name: "Productivity · Lo-fi",  count: 62 },
    veronica: { name: "Late Night · Soft",     count: 41 },
    sentinel: { name: "Silence · Ambient",     count: 12 },
  };
  const pl = modePlaylists[mode.id];
  return (
    <>
      <ToolHeader
        title="Spotify · Connected"
        sub={`device: MacBook · spotify_current`}
        action={<span className="status-pill ok">● linked</span>}
      />
      <div className="spt-now">
        <div className="spt-cover"><div className="spt-cover-inner">♪</div></div>
        <div className="spt-meta">
          <div className="spt-track">Sunset Lover · Reactor Mix</div>
          <div className="spt-artist">Petit Biscuit · Single</div>
          <div className="spt-bar">
            <div className="spt-bar-fill" style={{ width: "38%" }}></div>
          </div>
          <div className="spt-times mono"><span>1:54</span><span>5:02</span></div>
          <div className="spt-controls">
            <button className="spt-btn" onClick={() => onSend("spotify · previous track")}>⏮</button>
            <button className="spt-btn play" onClick={() => { setPlaying(!playing); onSend(playing ? "spotify · pause" : "spotify · resume"); }}>{playing ? "⏸" : "▶"}</button>
            <button className="spt-btn" onClick={() => onSend("spotify · next track")}>⏭</button>
            <div className="spt-vol">
              <span className="mono" style={{ fontSize: 10, color: "var(--ink-ghost)" }}>VOL</span>
              <div className="spt-vol-bar"><div className="spt-vol-fill" style={{ width: "62%" }}></div></div>
            </div>
          </div>
        </div>
      </div>
      <div className="divlabel-sm">Mode-armed playlists</div>
      <div className="tool-list">
        <Row left={<><span className="mode-mini active">{pl.name}</span></>} sub={`auto-arms with ${mode.label} · ${pl.count} tracks`} status={{ text: "ACTIVE", kind: "ok" }} onClick={() => onSend(`Play ${pl.name}.`)} />
        {Object.entries(modePlaylists).filter(([k]) => k !== mode.id).map(([k, p]) => (
          <Row key={k} left={<><span className="mode-mini">{p.name}</span></>} sub={`arms with ${k.toUpperCase()} · ${p.count} tracks`} onClick={() => onSend(`Play ${p.name}.`)} />
        ))}
      </div>
    </>
  );
}

/* ── HABITS ─────────────────────────────────────────────── */
function HabitsView({ onSend }) {
  const habits = [
    { name: "Morning pages",   freq: "daily",  streak: 14, done: true,  history: [1,1,1,1,1,1,1,1,1,1,1,1,1,1] },
    { name: "Workout",         freq: "daily",  streak: 4,  done: true,  history: [1,1,1,1,0,1,1,1,1,1,1,1,1,1] },
    { name: "No phone < 9am",  freq: "daily",  streak: 0,  done: false, history: [0,1,1,1,0,0,1,1,0,1,1,1,0,0] },
    { name: "Read 30min",      freq: "daily",  streak: 22, done: true,  history: [1,1,1,1,1,1,1,1,1,1,1,1,1,1] },
    { name: "Hydrate · 3L",    freq: "daily",  streak: 1,  done: false, history: [1,0,1,1,1,1,1,1,1,1,1,1,1,0] },
  ];
  const todayDone = habits.filter(h => h.done).length;
  return (
    <>
      <ToolHeader
        title="Habits · Today"
        sub={`${todayDone} / ${habits.length} complete · habit_status`}
        action={<button className="tool-action" onClick={() => onSend("Show my habit streaks.")}>Insights</button>}
      />
      <div className="tool-list">
        {habits.map((h, i) => (
          <div key={i} className="habit-row">
            <button
              className={`habit-tick ${h.done ? "done" : ""}`}
              onClick={() => onSend(`Log habit · ${h.name}.`)}
              aria-label={`Log ${h.name}`}
            >{h.done ? "✓" : ""}</button>
            <div className="habit-body">
              <div className="habit-name">{h.name}</div>
              <div className="habit-meta mono">{h.freq} · streak {h.streak}d</div>
            </div>
            <div className="habit-history">
              {h.history.map((d, j) => <div key={j} className={`habit-day ${d ? "on" : ""}`} title={`day -${14-j}`}></div>)}
            </div>
          </div>
        ))}
      </div>
      <div className="tool-compose">
        <div className="compose-grid">
          <input className="tool-input" placeholder="new habit name" />
          <select className="tool-input">
            <option>daily</option><option>weekday</option><option>weekend</option><option>weekly</option>
          </select>
        </div>
        <div className="tool-actions">
          <button className="tool-btn ghost" onClick={() => onSend("Create a new habit: 20min walk after lunch.")}>Create habit</button>
        </div>
      </div>
    </>
  );
}

/* ── NEWS ───────────────────────────────────────────────── */
function NewsView({ onSend }) {
  const feeds = [
    { feed: "Hacker News",   items: [
      { title: "Show HN: A local-first JARVIS in 700 lines of Python",  age: "2h", score: 412 },
      { title: "Why Ollama beat the API gateway in our stack",          age: "5h", score: 281 },
      { title: "The case against agent memory frameworks",              age: "8h", score: 144 },
    ]},
    { feed: "The Verge",     items: [
      { title: "Apple's new on-device LLM revealed at WWDC keynote",    age: "4h" },
      { title: "Tesla unveils next-gen humanoid spec",                  age: "9h" },
    ]},
    { feed: "Ars Technica",  items: [
      { title: "Linux kernel 7.0 ships with merged AI scheduler",       age: "1d" },
    ]},
  ];
  return (
    <>
      <ToolHeader
        title="News · Digest"
        sub="3 feeds · news_digest"
        action={<button className="tool-action" onClick={() => onSend("Summarize today's news digest.")}>Summarize</button>}
      />
      <div className="news-grid">
        {feeds.map((f, i) => (
          <div key={i} className="news-feed">
            <div className="news-feed-name">{f.feed}</div>
            <div className="news-items">
              {f.items.map((it, j) => (
                <div key={j} className="news-item" onClick={() => onSend(`Summarize "${it.title}".`)}>
                  <div className="news-title">{it.title}</div>
                  <div className="news-meta mono">{it.age}{it.score ? ` · ▲ ${it.score}` : ""}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="tool-compose">
        <input className="tool-input" placeholder="search topic · 'rust async', 'ai regulation' …" />
        <div className="tool-actions">
          <button className="tool-btn ghost" onClick={() => onSend("News on AI safety today.")}>Search news</button>
        </div>
      </div>
    </>
  );
}

/* ── OPERATIONS — tasks / reminders / notes ─────────────── */
function OpsView({ onSend }) {
  const [sub, setSub] = _useState("tasks");
  const tasks = [
    { t: "Finish reactor v3 spec",     pri: "P1", due: "today",    done: false },
    { t: "Reply to Yusuf",             pri: "P1", due: "today",    done: false },
    { t: "Push semantic memory branch", pri: "P2", due: "tomorrow", done: false },
    { t: "Renew domain",               pri: "P3", due: "Fri",      done: true  },
  ];
  const reminders = [
    { t: "Stand-up @ 09:00",   when: "in 12m",  fires: "soon" },
    { t: "Take meds",          when: "12:00",   fires: "" },
    { t: "Pickup laundry",     when: "18:30",   fires: "" },
  ];
  const notes = [
    { t: "Reactor v3 spec — section 4.2 safeties",  age: "today" },
    { t: "Quotes from Iyer book",                   age: "yest"  },
    { t: "Bug · pomodoro stale status after stop",  age: "2d"    },
  ];
  return (
    <>
      <ToolHeader
        title="Operations"
        sub="tasks · reminders · notes · memory"
        action={
          <div className="ops-tabs">
            {[
              { id: "tasks",     label: "Tasks" },
              { id: "reminders", label: "Reminders" },
              { id: "notes",     label: "Notes" },
            ].map(s => (
              <button key={s.id} className={`ops-tab ${sub === s.id ? "active" : ""}`} onClick={() => setSub(s.id)}>{s.label}</button>
            ))}
          </div>
        }
      />
      {sub === "tasks" && (
        <div className="tool-list">
          {tasks.map((t, i) => (
            <div key={i} className="habit-row">
              <button className={`habit-tick ${t.done ? "done" : ""}`} onClick={() => onSend(`Mark task done: ${t.t}.`)}>{t.done ? "✓" : ""}</button>
              <div className="habit-body">
                <div className="habit-name" style={{ textDecoration: t.done ? "line-through" : "none", opacity: t.done ? 0.6 : 1 }}>{t.t}</div>
                <div className="habit-meta mono">{t.pri} · due {t.due}</div>
              </div>
              <span className={`tool-pill ${t.pri === "P1" ? "crit" : t.pri === "P2" ? "warn" : ""}`}>{t.pri}</span>
            </div>
          ))}
        </div>
      )}
      {sub === "reminders" && (
        <div className="tool-list">
          {reminders.map((r, i) => (
            <Row key={i} left={<><span className="bell-ico">⏰</span><span className="mail-from">{r.t}</span></>} sub={`fires ${r.when}`} status={r.fires ? { text: "SOON", kind: "warn" } : null} right={r.when} />
          ))}
        </div>
      )}
      {sub === "notes" && (
        <div className="tool-list">
          {notes.map((n, i) => (
            <Row key={i} left={<><span className="note-ico mono">▤</span><span className="mail-from">{n.t}</span></>} right={n.age} onClick={() => onSend(`Open note: ${n.t}.`)} />
          ))}
        </div>
      )}
      <div className="tool-compose">
        <input className="tool-input" placeholder={`add ${sub.slice(0, -1)}…`} />
        <div className="tool-actions">
          <button className="tool-btn ghost" onClick={() => onSend(`Add a ${sub.slice(0,-1)}.`)}>Add</button>
        </div>
      </div>
    </>
  );
}

/* ── CLIPBOARD ──────────────────────────────────────────── */
function ClipView({ onSend }) {
  const clips = [
    { content: "ssh aarav@reactor.local -p 2222",         tags: "ssh, server",   age: "12m" },
    { content: "OLLAMA_BASE_URL=http://127.0.0.1:11434/v1", tags: "env, ollama",   age: "2h" },
    { content: "https://github.com/Beastburner/Veronica/issues/142", tags: "github, issue", age: "5h" },
    { content: "\"The work is the work.\" — somebody, probably",     tags: "quote",         age: "1d" },
  ];
  return (
    <>
      <ToolHeader
        title="Clipboard · Saved"
        sub={`${clips.length} clips indexed · clipboard_search`}
        action={<button className="tool-action" onClick={() => onSend("Save my last clipboard.")}>Save current</button>}
      />
      <div className="tool-list">
        {clips.map((c, i) => (
          <Row
            key={i}
            left={<span className="clip-text mono">{c.content}</span>}
            sub={`tags: ${c.tags}`}
            right={c.age}
            onClick={() => onSend(`Recall clip: ${c.content.slice(0, 30)}…`)}
          />
        ))}
      </div>
      <div className="tool-compose">
        <input className="tool-input" placeholder="search clips by content or tag…" />
        <div className="tool-actions">
          <button className="tool-btn ghost" onClick={() => onSend("Search clipboard for ssh.")}>Search</button>
        </div>
      </div>
    </>
  );
}

/* ── POMODORO ──────────────────────────────────────────── */
function PomodoroView({ onSend }) {
  const [running, setRunning] = _useState(true);
  const [label, setLabel] = _useState("Reactor v3 spec");
  const remaining = 14 * 60 + 22; // 14:22
  const pct = 41;
  const fmt = (s) => `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`;
  return (
    <>
      <ToolHeader
        title="Pomodoro · Focus"
        sub="25 / 5 minute cycle · pomodoro_status"
        action={<span className={`status-pill ${running ? "ok" : ""}`}>{running ? "● running" : "○ idle"}</span>}
      />
      <div className="pom-card">
        <div className="pom-ring">
          <svg viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="52" fill="none" stroke="var(--accent-border)" strokeWidth="2" />
            <circle
              cx="60" cy="60" r="52" fill="none"
              stroke="var(--accent-strong)" strokeWidth="3"
              strokeDasharray={`${(pct/100) * 2 * Math.PI * 52} ${2 * Math.PI * 52}`}
              strokeDashoffset="0"
              transform="rotate(-90 60 60)"
              strokeLinecap="round"
              style={{ filter: `drop-shadow(0 0 6px var(--accent-glow))` }}
            />
            <text x="60" y="58" textAnchor="middle" fontFamily="JetBrains Mono" fontSize="18" fontWeight="600" fill="var(--ink)">{fmt(remaining)}</text>
            <text x="60" y="76" textAnchor="middle" fontFamily="JetBrains Mono" fontSize="8" fill="var(--ink-ghost)" letterSpacing="2">REMAINING</text>
          </svg>
        </div>
        <div className="pom-meta">
          <div><div className="k">Working on</div><div className="v">{label}</div></div>
          <div><div className="k">Cycle</div><div className="v mono">2 / 4</div></div>
          <div><div className="k">Today</div><div className="v mono">1h 32m focused</div></div>
        </div>
      </div>
      <div className="tool-compose">
        <input className="tool-input" placeholder="task label" value={label} onChange={(e) => setLabel(e.target.value)} />
        <div className="tool-actions">
          {running ? (
            <>
              <button className="tool-btn" onClick={() => { setRunning(false); onSend("Pause the pomodoro timer."); }}>Pause</button>
              <button className="tool-btn danger" onClick={() => { setRunning(false); onSend("Stop the pomodoro timer."); }}>Stop</button>
            </>
          ) : (
            <button className="tool-btn ghost" onClick={() => { setRunning(true); onSend(`Start a 25-minute focus block on "${label}".`); }}>Start 25:00</button>
          )}
        </div>
      </div>
    </>
  );
}

/* ── WEB SEARCH / SCRAPE ────────────────────────────────── */
function SearchView({ onSend }) {
  const results = [
    { title: "Local-first AI: a primer (paper)",    url: "arxiv.org/abs/2401.04212", snippet: "We define local-first AI as systems where inference, memory, and user data all reside on…" },
    { title: "Ollama Documentation · Quickstart",  url: "ollama.ai/docs/quickstart", snippet: "Ollama lets you run open-source large language models, such as Llama 2, locally. Quickstart…" },
    { title: "Anthropic — Building agents that act safely", url: "anthropic.com/research", snippet: "We describe a confirmation-first pattern where irreversible actions surface a preview before…" },
  ];
  return (
    <>
      <ToolHeader title="Web · Search + Scrape" sub="DuckDuckGo · web_search / web_scrape" action={<button className="tool-action" onClick={() => onSend("Search the web for local-first AI.")}>Search</button>} />
      <div className="tool-list">
        {results.map((r, i) => (
          <Row
            key={i}
            left={<span className="mail-from">{r.title}</span>}
            sub={`${r.url} — ${r.snippet}`}
            right="→"
            onClick={() => onSend(`Scrape ${r.url}.`)}
          />
        ))}
      </div>
      <div className="tool-compose">
        <input className="tool-input" placeholder="query · or paste a URL to scrape" />
        <div className="tool-actions">
          <button className="tool-btn ghost" onClick={() => onSend("Search the web for Veronica.")}>Search</button>
          <button className="tool-btn" onClick={() => onSend("Scrape the front page of HN.")}>Scrape URL</button>
        </div>
      </div>
    </>
  );
}

/* ── PLANNER ────────────────────────────────────────────── */
function PlannerView({ onSend }) {
  const [goal, setGoal] = _useState("Ship reactor v3 spec before Friday");
  const steps = [
    { n: 1, t: "Draft section 4.2 safeties",      due: "Tue 17:00", dep: "—",        risk: "low"  },
    { n: 2, t: "Get Yusuf review on draft",        due: "Wed 12:00", dep: "step 1",   risk: "low"  },
    { n: 3, t: "Address review notes",             due: "Wed 18:00", dep: "step 2",   risk: "med"  },
    { n: 4, t: "Final pass + figures",             due: "Thu 14:00", dep: "step 3",   risk: "med"  },
    { n: 5, t: "Submit to design review",          due: "Fri 09:00", dep: "step 4",   risk: "high" },
  ];
  return (
    <>
      <ToolHeader title="Goal Planner" sub="multi-step decomposition · plan_goal" action={<button className="tool-action" onClick={() => onSend(`Plan: ${goal}`)}>Decompose</button>} />
      <div className="tool-compose">
        <textarea className="tool-textarea" rows={2} value={goal} onChange={(e) => setGoal(e.target.value)}></textarea>
      </div>
      <div className="planner-chain">
        {steps.map((s, i) => (
          <div key={s.n} className="plan-step">
            <div className={`plan-num mono ${s.risk}`}>{String(s.n).padStart(2, "0")}</div>
            <div className="plan-body">
              <div className="plan-title">{s.t}</div>
              <div className="plan-meta mono">due {s.due} · depends on {s.dep} · risk <span className={`risk-${s.risk}`}>{s.risk}</span></div>
            </div>
            {i < steps.length - 1 ? <div className="plan-line"></div> : null}
          </div>
        ))}
      </div>
      <div className="tool-actions" style={{ padding: "0 14px 14px" }}>
        <button className="tool-btn ghost" onClick={() => onSend("Auto-create these 5 tasks.")}>Auto-create as tasks</button>
      </div>
    </>
  );
}

/* ── Tool root ──────────────────────────────────────────── */
function ToolSurfaces({ onSend, mode }) {
  const [tab, setTab] = _useState("mail");
  const active = TOOL_TABS.find((t) => t.id === tab);
  return (
    <div className="hud tools-hud">
      <div className="section-head">
        <span className="title">⌬ Tool Surfaces · {active.label}</span>
        <span className="meta">{TOOL_TABS.length} tools · backend = tools.py</span>
      </div>
      <div className="tools">
        <div className="tools-rail" role="tablist">
          {TOOL_TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              className={`tools-tab ${tab === t.id ? "active" : ""}`}
              onClick={() => setTab(t.id)}
              title={t.label}
            >
              <span className="tools-glyph">{t.glyph}</span>
              <span className="tools-tablabel mono">{t.short}</span>
            </button>
          ))}
        </div>
        <div className="tools-content">
          {tab === "mail"      && <MailView      onSend={onSend} />}
          {tab === "calendar"  && <CalendarView  onSend={onSend} />}
          {tab === "whatsapp"  && <WhatsAppView  onSend={onSend} />}
          {tab === "github"    && <GitHubView    onSend={onSend} />}
          {tab === "spotify"   && <SpotifyView   onSend={onSend} mode={mode} />}
          {tab === "habits"    && <HabitsView    onSend={onSend} />}
          {tab === "news"      && <NewsView      onSend={onSend} />}
          {tab === "ops"       && <OpsView       onSend={onSend} />}
          {tab === "clipboard" && <ClipView      onSend={onSend} />}
          {tab === "pomodoro"  && <PomodoroView  onSend={onSend} />}
          {tab === "search"    && <SearchView    onSend={onSend} />}
          {tab === "planner"   && <PlannerView   onSend={onSend} />}
        </div>
      </div>
    </div>
  );
}

window.ToolSurfaces = ToolSurfaces;


/* ── VERONICA — Reactor Core Command Center ──────────────── */

:root {
  color-scheme: dark;

  /* JARVIS — Arc Light (default) */
  --accent:        rgb(56 232 255 / 0.85);
  --accent-strong: rgb(56 232 255);
  --accent-text:   #d6f7ff;
  --accent-glow:   rgba(56, 232, 255, 0.45);
  --accent-hex:    #38e8ff;
  --accent-dim:    rgba(56, 232, 255, 0.55);
  --accent-border: rgba(56, 232, 255, 0.22);
  --accent-shadow: rgba(56, 232, 255, 0.18);

  --void-deep:  #04060a;
  --void-mid:   #0a0f17;
  --void-panel: rgba(5, 10, 16, 0.72);

  --ink:        #eefbff;
  --ink-dim:    #94a3b8;
  --ink-ghost:  #475569;
}

[data-mode="friday"] {
  --accent:        rgb(255 209 102 / 0.85);
  --accent-strong: rgb(255 209 102);
  --accent-text:   #fff4d2;
  --accent-glow:   rgba(255, 209, 102, 0.45);
  --accent-hex:    #ffd166;
  --accent-dim:    rgba(255, 209, 102, 0.55);
  --accent-border: rgba(255, 209, 102, 0.22);
  --accent-shadow: rgba(255, 209, 102, 0.18);
}

[data-mode="veronica"] {
  --accent:        rgb(178 132 255 / 0.85);
  --accent-strong: rgb(178 132 255);
  --accent-text:   #ece2ff;
  --accent-glow:   rgba(178, 132, 255, 0.45);
  --accent-hex:    #b284ff;
  --accent-dim:    rgba(178, 132, 255, 0.55);
  --accent-border: rgba(178, 132, 255, 0.22);
  --accent-shadow: rgba(178, 132, 255, 0.18);
}

[data-mode="sentinel"] {
  --accent:        rgb(255 95 109 / 0.85);
  --accent-strong: rgb(255 95 109);
  --accent-text:   #ffd9dc;
  --accent-glow:   rgba(255, 95, 109, 0.45);
  --accent-hex:    #ff5f6d;
  --accent-dim:    rgba(255, 95, 109, 0.55);
  --accent-border: rgba(255, 95, 109, 0.22);
  --accent-shadow: rgba(255, 95, 109, 0.18);
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }

body {
  min-height: 100vh;
  font-family: 'Space Grotesk', system-ui, -apple-system, sans-serif;
  color: var(--ink);
  background:
    radial-gradient(circle at 50% 0%, var(--accent-shadow), transparent 38rem),
    radial-gradient(circle at 85% 100%, rgba(255, 63, 129, 0.04), transparent 30rem),
    linear-gradient(180deg, #04060a 0%, #060a12 50%, #04060a 100%);
  background-attachment: fixed;
  overflow-x: hidden;
  letter-spacing: 0.005em;
  -webkit-font-smoothing: antialiased;
  transition: background 0.5s ease;
}

.mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
.label {
  font-size: 10.5px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--accent-text);
  font-weight: 500;
}

/* ── HUD panel core ───────────────────────────────────────── */
.hud {
  position: relative;
  background: var(--void-panel);
  border: 1px solid var(--accent-border);
  border-radius: 4px;
  box-shadow:
    0 0 28px var(--accent-shadow),
    inset 0 0 24px rgba(2, 5, 9, 0.6);
  backdrop-filter: blur(18px);
  transition: border-color 0.4s ease, box-shadow 0.4s ease;
}
.hud::before,
.hud::after {
  content: "";
  position: absolute;
  width: 14px;
  height: 14px;
  border-color: var(--accent-dim);
  border-style: solid;
  pointer-events: none;
  z-index: 2;
  transition: border-color 0.4s ease;
}
.hud::before {
  top: -1px; left: -1px;
  border-width: 2px 0 0 2px;
}
.hud::after {
  bottom: -1px; right: -1px;
  border-width: 0 2px 2px 0;
}

.hud.compact {
  padding: 14px 16px;
}

/* ── Scanlines ambient ───────────────────────────────────── */
.scanlines {
  position: fixed; inset: 0;
  background-image: linear-gradient(rgba(255,255,255,0.022) 1px, transparent 1px);
  background-size: 100% 4px;
  pointer-events: none;
  opacity: 0.5;
  z-index: 1;
  mix-blend-mode: screen;
}

.scan-sweep {
  position: fixed; top: 0; left: 0;
  width: 2px; height: 100vh;
  background: linear-gradient(to bottom, transparent, var(--accent-border), transparent);
  pointer-events: none;
  animation: h-scan 9s linear infinite;
  z-index: 1;
}
@keyframes h-scan {
  0%   { transform: translateX(-2vw); }
  100% { transform: translateX(102vw); }
}

/* ── Top status rail ─────────────────────────────────────── */
.rail {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 10px 18px;
  background: linear-gradient(180deg, rgba(5,10,16,0.85), rgba(5,10,16,0.55));
  border-bottom: 1px solid var(--accent-border);
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-dim);
}
.rail .brand {
  display: flex; align-items: center; gap: 10px;
  color: var(--accent-text);
  font-weight: 600;
  letter-spacing: 0.32em;
}
.rail .brand-mark {
  width: 22px; height: 22px;
  border: 1px solid var(--accent-dim);
  border-radius: 2px;
  position: relative;
  display: grid; place-items: center;
  background: rgba(0,0,0,0.4);
}
.rail .brand-mark::after {
  content: "";
  width: 8px; height: 8px;
  background: var(--accent-strong);
  border-radius: 50%;
  box-shadow: 0 0 10px var(--accent-strong);
}
.rail .segment {
  display: flex; align-items: center; gap: 8px;
}
.rail .seg-key { color: var(--ink-ghost); }
.rail .seg-val { color: var(--ink); font-family: 'JetBrains Mono', monospace; letter-spacing: 0.08em; text-transform: none; }
.rail .spacer { flex: 1; }
.rail .status-pill {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 3px 10px;
  border: 1px solid var(--accent-border);
  border-radius: 2px;
  background: rgba(56, 232, 255, 0.06);
  color: var(--accent-text);
  font-size: 10px;
}
.dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent-strong);
  box-shadow: 0 0 8px var(--accent-strong);
  animation: status-blink 2.4s ease-in-out infinite;
}
@keyframes status-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

/* ── Grid layout ─────────────────────────────────────────── */
.shell {
  display: grid;
  grid-template-columns: 280px 1fr 320px;
  gap: 14px;
  padding: 14px;
  max-width: 1680px;
  margin: 0 auto;
  position: relative;
  z-index: 2;
}

@media (max-width: 1180px) {
  .shell { grid-template-columns: 240px 1fr 280px; }
}
@media (max-width: 980px) {
  .shell { grid-template-columns: 1fr; }
}

.col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }

/* ── Mode card ───────────────────────────────────────────── */
.mode-list { display: flex; flex-direction: column; gap: 6px; }
.mode-btn {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 11px 12px;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 3px;
  text-align: left;
  cursor: pointer;
  color: var(--ink-dim);
  font-family: inherit;
  transition: border-color 0.2s ease, background 0.2s ease, color 0.2s ease;
}
.mode-btn:hover {
  border-color: var(--accent-border);
  color: var(--ink);
}
.mode-btn .mode-glyph {
  width: 22px; height: 22px;
  border: 1px solid currentColor;
  border-radius: 2px;
  display: grid; place-items: center;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  opacity: 0.7;
}
.mode-btn .mode-name {
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.22em;
}
.mode-btn .mode-sub {
  font-size: 10.5px;
  color: var(--ink-ghost);
  letter-spacing: 0.04em;
  text-transform: none;
  margin-top: 1px;
}
.mode-btn .mode-key {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--ink-ghost);
  padding: 2px 6px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 2px;
}
.mode-btn.active {
  border-color: var(--accent-strong);
  background: rgba(255,255,255,0.04);
  color: var(--ink);
  animation: reactor-pulse 2.6s ease-in-out infinite;
}
.mode-btn.active .mode-glyph {
  color: var(--accent-strong);
  background: var(--accent-shadow);
  opacity: 1;
  box-shadow: 0 0 12px var(--accent-shadow);
}
.mode-btn.active .mode-key { color: var(--accent-text); border-color: var(--accent-border); }

@keyframes reactor-pulse {
  0%,100% { box-shadow: 0 0 0 1px var(--accent-border), 0 0 14px var(--accent-shadow); }
  50%     { box-shadow: 0 0 0 1px var(--accent-strong), 0 0 26px var(--accent-glow); }
}

/* ── Section heading ────────────────────────────────────── */
.section-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px 6px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.section-head .title {
  font-size: 10.5px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--accent-text);
  font-weight: 600;
  display: flex; align-items: center; gap: 8px;
}
.section-head .meta {
  font-size: 10px;
  letter-spacing: 0.1em;
  color: var(--ink-ghost);
  font-family: 'JetBrains Mono', monospace;
}

.section-body { padding: 12px 14px 14px; }

/* ── Reactor center ─────────────────────────────────────── */
.reactor-hud { padding: 0; }
.neural-wrap {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 18px;
  padding: 22px 18px 14px;
  align-items: center;
  position: relative;
}
.neural-stat-col {
  display: flex; flex-direction: column;
  gap: 14px;
}
.neural-stat-col.right { align-items: flex-end; text-align: right; }
.neural-stat .k {
  font-size: 9px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--ink-ghost);
  font-family: 'JetBrains Mono', monospace;
}
.neural-stat .v {
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  color: var(--ink);
  letter-spacing: 0.04em;
  margin-top: 2px;
  font-weight: 500;
}
.neural-stat .v.accent {
  color: var(--accent-text);
  text-shadow: 0 0 8px var(--accent-shadow);
}
.mini-bar {
  height: 2px;
  background: rgba(255,255,255,0.06);
  border-radius: 1px;
  overflow: hidden;
  margin-top: 4px;
  width: 100%;
  max-width: 110px;
}
.neural-stat-col.right .mini-bar { margin-left: auto; }
.mini-bar-fill {
  height: 100%;
  background: var(--accent-strong);
  box-shadow: 0 0 6px var(--accent-glow);
  transition: width 0.5s ease;
}

.neural-core-wrap {
  width: 360px;
  height: 360px;
  position: relative;
  display: grid; place-items: center;
}
.neural-core-wrap svg {
  width: 100%; height: 100%; display: block;
}
.neural-overlay-label {
  position: absolute;
  font-size: 8.5px;
  letter-spacing: 0.32em;
  color: var(--accent-text);
  opacity: 0.7;
  text-transform: uppercase;
  pointer-events: none;
  white-space: nowrap;
}
.neural-overlay-label.top { top: 2px;    left: 50%; transform: translateX(-50%); }
.neural-overlay-label.bottom { bottom: 2px; left: 50%; transform: translateX(-50%); }

@media (max-width: 1320px) {
  .neural-core-wrap { width: 300px; height: 300px; }
}
@media (max-width: 1100px) {
  .neural-wrap { grid-template-columns: 1fr; gap: 10px; padding: 14px; }
  .neural-stat-col,
  .neural-stat-col.right { flex-direction: row; flex-wrap: wrap; align-items: stretch; text-align: left; gap: 14px; }
  .neural-stat-col.right .mini-bar { margin-left: 0; }
}

/* live data strip */
.neural-strip {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 0;
  border-top: 1px solid rgba(255,255,255,0.06);
  border-bottom: 1px solid rgba(255,255,255,0.06);
  background: rgba(0,0,0,0.35);
}
.strip-cell {
  display: flex; flex-direction: column; gap: 2px;
  padding: 9px 12px;
  border-right: 1px solid rgba(255,255,255,0.05);
  min-width: 0;
}
.strip-cell:last-child { border-right: none; }
.strip-cell .k {
  font-size: 8.5px;
  letter-spacing: 0.24em;
  color: var(--ink-ghost);
  text-transform: uppercase;
}
.strip-cell .v {
  font-size: 11.5px;
  color: var(--ink);
  letter-spacing: 0.04em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.strip-cell .v.ok { color: var(--accent-strong); text-shadow: 0 0 6px var(--accent-glow); }

@media (max-width: 980px) {
  .neural-strip { grid-template-columns: 1fr 1fr; }
}

/* legacy reactor-wrap kept for fallback (unused now) */
.reactor-wrap { display: none; }

.reactor-foot {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px 14px;
  border-top: 1px solid rgba(255,255,255,0.05);
  font-size: 11px;
  color: var(--ink-dim);
}
.reactor-foot .mode-pill {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 4px 10px;
  border: 1px solid var(--accent-border);
  background: rgba(0,0,0,0.4);
  border-radius: 2px;
  color: var(--accent-text);
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}
.reactor-foot .brief {
  flex: 1;
  margin: 0 16px;
  text-align: center;
  color: var(--ink-dim);
  font-size: 11.5px;
  letter-spacing: 0.04em;
}

/* ── Chat ───────────────────────────────────────────────── */
.chat {
  display: flex; flex-direction: column;
  min-height: 360px;
}
.chat-feed {
  flex: 1;
  padding: 14px 14px 8px;
  overflow-y: auto;
  display: flex; flex-direction: column; gap: 10px;
  max-height: 380px;
}
.bubble {
  border: 1px solid;
  border-radius: 3px;
  padding: 11px 14px;
  font-size: 13px;
  line-height: 1.55;
  position: relative;
  animation: msg-in 0.25s ease-out both;
}
.bubble .who {
  font-size: 9.5px;
  letter-spacing: 0.26em;
  text-transform: uppercase;
  margin-bottom: 4px;
  color: var(--ink-ghost);
  font-weight: 600;
}
.bubble.veronica {
  border-color: var(--accent-border);
  background: linear-gradient(180deg, rgba(56,232,255,0.04), rgba(0,0,0,0.2));
  color: var(--accent-text);
  max-width: 90%;
}
.bubble.veronica .who { color: var(--accent-text); }
.bubble.commander {
  border-color: rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.02);
  color: var(--ink);
  max-width: 85%;
  margin-left: auto;
}
.bubble.commander .who { color: var(--ink-dim); text-align: right; }
.bubble.system {
  border-color: rgba(255,255,255,0.05);
  background: transparent;
  color: var(--ink-ghost);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  padding: 6px 10px;
  text-align: center;
  letter-spacing: 0.1em;
  border-radius: 2px;
}
@keyframes msg-in {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.bubble .cursor {
  display: inline-block;
  width: 6px; height: 14px;
  background: var(--accent-strong);
  vertical-align: -2px;
  margin-left: 2px;
  animation: blink 1s steps(2) infinite;
}
@keyframes blink { 50% { opacity: 0; } }

.tool-line {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-ghost);
  display: flex; gap: 6px; align-items: center;
  margin-top: 6px;
}
.tool-line .ok { color: var(--accent-strong); }

/* command bar */
.command-bar {
  display: flex; gap: 0;
  margin: 0 14px 14px;
  border: 1px solid var(--accent-border);
  border-radius: 3px;
  background: rgba(0,0,0,0.45);
  overflow: hidden;
  transition: border-color 0.2s ease;
}
.command-bar:focus-within {
  border-color: var(--accent-strong);
  box-shadow: 0 0 0 1px var(--accent-shadow);
}
.command-bar .prompt {
  display: grid; place-items: center;
  padding: 0 12px;
  color: var(--accent-strong);
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  border-right: 1px solid var(--accent-border);
}
.command-bar input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--ink);
  font-family: inherit;
  font-size: 13.5px;
  padding: 12px 12px;
  min-width: 0;
}
.command-bar input::placeholder { color: var(--ink-ghost); }
.command-bar .send {
  background: transparent;
  border: none;
  border-left: 1px solid var(--accent-border);
  color: var(--accent-text);
  font-size: 11px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  padding: 0 16px;
  cursor: pointer;
  transition: background 0.15s ease;
  font-family: inherit;
  font-weight: 600;
}
.command-bar .send:hover { background: var(--accent-shadow); }
.command-bar .send:disabled { opacity: 0.4; cursor: not-allowed; }
.command-bar .mic {
  background: transparent;
  border: none;
  border-left: 1px solid var(--accent-border);
  color: var(--accent-text);
  padding: 0 14px;
  cursor: pointer;
  display: grid; place-items: center;
}
.command-bar .mic:hover { background: var(--accent-shadow); }

/* ── Telemetry ──────────────────────────────────────────── */
.tele-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
}
.tele-row {
  display: flex; flex-direction: column; gap: 6px;
}
.tele-row .top {
  display: flex; justify-content: space-between; align-items: baseline;
}
.tele-row .k {
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--ink-ghost);
}
.tele-row .v {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--ink);
}
.bar {
  height: 4px;
  background: rgba(255,255,255,0.06);
  border-radius: 1px;
  overflow: hidden;
  position: relative;
}
.bar-fill {
  height: 100%;
  background: var(--accent-strong);
  box-shadow: 0 0 8px var(--accent-glow);
  transition: width 0.6s ease;
}
.bar-fill.warn { background: #fb923c; box-shadow: 0 0 8px rgba(251,146,60,0.5); }
.bar-fill.crit { background: #ff5f6d; box-shadow: 0 0 8px rgba(255,95,109,0.5); }

.tele-row .scale {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9.5px;
  color: var(--ink-ghost);
  margin-top: 2px;
}

.full-row { grid-column: 1 / -1; }

/* sparkline */
.spark {
  display: flex; align-items: flex-end; gap: 2px;
  height: 28px;
}
.spark .bar-tick {
  flex: 1;
  background: var(--accent-strong);
  opacity: 0.7;
  border-radius: 1px 1px 0 0;
  min-height: 2px;
  transition: height 0.5s ease;
}
.spark .bar-tick:last-child { opacity: 1; box-shadow: 0 0 6px var(--accent-glow); }

/* ── Lists (protocols / alerts / activity) ──────────────── */
.list-item {
  display: grid;
  grid-template-columns: 16px 1fr auto;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 2px;
  border: 1px solid rgba(255,255,255,0.05);
  background: rgba(255,255,255,0.015);
  font-size: 12px;
  color: var(--ink);
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease;
  align-items: center;
}
.list-item:hover {
  border-color: var(--accent-border);
  background: var(--accent-shadow);
}
.list-item .ico {
  width: 14px; height: 14px;
  border-radius: 50%;
  background: rgba(255,255,255,0.06);
  display: grid; place-items: center;
  font-size: 9px;
  color: var(--accent-text);
  font-family: 'JetBrains Mono', monospace;
}
.list-item .desc {
  display: flex; flex-direction: column; gap: 1px;
  min-width: 0;
}
.list-item .desc .t { font-size: 12.5px; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.list-item .desc .s { font-size: 10.5px; color: var(--ink-ghost); letter-spacing: 0.02em; }
.list-item .badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9.5px;
  color: var(--ink-ghost);
  letter-spacing: 0.08em;
}

.list { display: flex; flex-direction: column; gap: 6px; }

/* alert variants */
.list-item.alert-warn { border-color: rgba(251,146,60,0.25); background: rgba(251,146,60,0.04); }
.list-item.alert-warn .ico { background: rgba(251,146,60,0.18); color: #fdba74; }
.list-item.alert-crit { border-color: rgba(255,95,109,0.3); background: rgba(255,95,109,0.05); }
.list-item.alert-crit .ico { background: rgba(255,95,109,0.2); color: #fda4af; }

/* ── Toggle row (security rules) ────────────────────────── */
.rule-row {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px dashed rgba(255,255,255,0.06);
  font-size: 12px;
  color: var(--ink-dim);
}
.rule-row:last-child { border-bottom: none; }
.rule-row .pill {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9.5px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 2px;
  border: 1px solid var(--accent-border);
  color: var(--accent-text);
  background: rgba(0,0,0,0.4);
}
.rule-row .pill.off { color: var(--ink-ghost); border-color: rgba(255,255,255,0.1); }

/* ── Activity feed ──────────────────────────────────────── */
.activity {
  display: flex; flex-direction: column; gap: 0;
  position: relative;
}
.activity .row {
  display: grid;
  grid-template-columns: 70px 1fr;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px dashed rgba(255,255,255,0.05);
  font-size: 11.5px;
}
.activity .row:last-child { border-bottom: none; }
.activity .row .t {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  color: var(--ink-ghost);
  letter-spacing: 0.04em;
}
.activity .row .what { color: var(--ink); }
.activity .row .what .tag {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9.5px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  border: 1px solid var(--accent-border);
  border-radius: 2px;
  color: var(--accent-text);
  background: rgba(0,0,0,0.3);
}
.activity .row .what .tag.warn { color: #fdba74; border-color: rgba(251,146,60,0.3); }

/* ── Ghost buttons (suggestions / protocols) ────────────── */
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 14px 12px; }
.chip {
  font-family: inherit;
  font-size: 11px;
  padding: 6px 10px;
  border: 1px solid var(--accent-border);
  background: rgba(0,0,0,0.4);
  color: var(--accent-text);
  border-radius: 2px;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
  letter-spacing: 0.04em;
}
.chip:hover {
  background: var(--accent-shadow);
  border-color: var(--accent-strong);
}
.chip .glyph {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  margin-right: 6px;
  color: var(--accent-strong);
  opacity: 0.8;
}

/* ── Briefing card ──────────────────────────────────────── */
.brief-card {
  padding: 14px 16px;
  border-top: 1px solid rgba(255,255,255,0.05);
  font-size: 13px;
  color: var(--ink);
  line-height: 1.6;
  display: flex; gap: 14px; align-items: flex-start;
}
.brief-card .corner {
  width: 28px; height: 28px;
  border: 1px solid var(--accent-border);
  border-radius: 2px;
  display: grid; place-items: center;
  flex-shrink: 0;
  color: var(--accent-strong);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  background: var(--accent-shadow);
}
.brief-card .text { color: var(--ink-dim); }
.brief-card .text strong { color: var(--accent-text); font-weight: 600; }

/* ── Small divider label ───────────────────────────────── */
.divlabel {
  display: flex; align-items: center; gap: 10px;
  font-size: 9.5px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--ink-ghost);
  margin: 6px 14px 10px;
}
.divlabel::after {
  content: ""; flex: 1; height: 1px; background: rgba(255,255,255,0.05);
}

/* footer status */
.footer-rail {
  display: flex; justify-content: space-between;
  padding: 8px 18px;
  border-top: 1px solid var(--accent-border);
  background: rgba(0,0,0,0.4);
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--ink-ghost);
  letter-spacing: 0.1em;
  position: relative; z-index: 2;
}
.footer-rail .group { display: flex; gap: 18px; }
.footer-rail .ok { color: var(--accent-strong); }

/* hide scrollbar fancier */
.chat-feed::-webkit-scrollbar { width: 4px; }
.chat-feed::-webkit-scrollbar-track { background: transparent; }
.chat-feed::-webkit-scrollbar-thumb { background: var(--accent-border); border-radius: 2px; }

/* ════════════════════════════════════════════════════════════ */
/* ── TOOL SURFACES ─────────────────────────────────────────── */
/* ════════════════════════════════════════════════════════════ */

.tools-hud { padding: 0; }
.tools {
  display: grid;
  grid-template-columns: 84px 1fr;
  min-height: 480px;
}

.tools-rail {
  display: flex; flex-direction: column;
  gap: 2px;
  padding: 8px 6px 8px 8px;
  border-right: 1px solid rgba(255,255,255,0.06);
  background: rgba(0,0,0,0.25);
}
.tools-tab {
  display: flex; flex-direction: column; align-items: center; gap: 3px;
  padding: 9px 4px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 3px;
  cursor: pointer;
  color: var(--ink-ghost);
  font-family: inherit;
  transition: background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}
.tools-tab:hover {
  color: var(--ink);
  background: rgba(255,255,255,0.03);
}
.tools-tab.active {
  color: var(--accent-text);
  background: var(--accent-shadow);
  border-color: var(--accent-border);
}
.tools-tab.active .tools-glyph {
  color: var(--accent-strong);
  text-shadow: 0 0 10px var(--accent-glow);
}
.tools-glyph {
  font-size: 17px;
  line-height: 1;
}
.tools-tablabel {
  font-size: 8.5px;
  letter-spacing: 0.16em;
}

.tools-content {
  display: flex; flex-direction: column;
  min-width: 0;
  max-height: 720px;
  overflow-y: auto;
}
.tools-content::-webkit-scrollbar { width: 4px; }
.tools-content::-webkit-scrollbar-track { background: transparent; }
.tools-content::-webkit-scrollbar-thumb { background: var(--accent-border); border-radius: 2px; }

/* ── Tool header ───────────────────────────────────────── */
.tool-header {
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
  padding: 14px 16px 10px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.tool-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: 0.04em;
}
.tool-sub {
  font-size: 10.5px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--ink-ghost);
  letter-spacing: 0.04em;
  margin-top: 2px;
}
.tool-action {
  background: transparent;
  border: 1px solid var(--accent-border);
  color: var(--accent-text);
  padding: 5px 12px;
  font-family: inherit;
  font-size: 10.5px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  border-radius: 2px;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
}
.tool-action:hover {
  background: var(--accent-shadow);
  border-color: var(--accent-strong);
}

/* ── Tool list / rows ──────────────────────────────────── */
.tool-list {
  display: flex; flex-direction: column;
  padding: 8px 14px;
  gap: 2px;
}
.tool-row {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 9px 10px;
  border: 1px solid transparent;
  border-radius: 3px;
  transition: background 0.15s ease, border-color 0.15s ease;
  min-width: 0;
}
.tool-row.clickable { cursor: pointer; }
.tool-row.clickable:hover {
  background: rgba(255,255,255,0.025);
  border-color: var(--accent-border);
}
.tool-row-main { min-width: 0; }
.tool-row-left {
  display: flex; align-items: center; gap: 9px;
  font-size: 12.5px;
  color: var(--ink);
  min-width: 0;
}
.tool-row-sub {
  font-size: 11px;
  color: var(--ink-ghost);
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.01em;
}
.tool-row-right {
  display: flex; align-items: center; gap: 8px;
  flex-shrink: 0;
}
.tool-row-meta {
  font-size: 10px;
  color: var(--ink-ghost);
  letter-spacing: 0.08em;
}
.tool-pill {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  letter-spacing: 0.18em;
  padding: 2px 7px;
  border-radius: 2px;
  border: 1px solid var(--accent-border);
  color: var(--accent-text);
  background: rgba(0,0,0,0.4);
}
.tool-pill.warn { color: #fdba74; border-color: rgba(251,146,60,0.35); background: rgba(251,146,60,0.06); }
.tool-pill.crit { color: #fda4af; border-color: rgba(255,95,109,0.35); background: rgba(255,95,109,0.06); }
.tool-pill.ok   { color: var(--accent-strong); }
.tool-pill.count {
  background: var(--accent-strong);
  color: #04060a;
  border-color: var(--accent-strong);
  font-weight: 600;
  letter-spacing: 0;
}

.status-pill.ok { color: var(--accent-strong); border-color: var(--accent-border); }

/* ── Mail specifics ────────────────────────────────────── */
.mail-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: transparent;
  border: 1px solid rgba(255,255,255,0.15);
  flex-shrink: 0;
}
.mail-dot.unread { background: var(--accent-strong); border-color: var(--accent-strong); box-shadow: 0 0 6px var(--accent-glow); }
.mail-dot.imp.unread { background: #fdba74; border-color: #fdba74; box-shadow: 0 0 6px rgba(251,146,60,0.5); }

.mail-from {
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
  flex-shrink: 0;
}
.mail-subject {
  color: var(--ink-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
}

/* compose */
.tool-compose {
  padding: 12px 14px 14px;
  border-top: 1px solid rgba(255,255,255,0.05);
  display: flex; flex-direction: column; gap: 8px;
}
.compose-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.compose-grid.three { grid-template-columns: 1.4fr 1fr 1fr; }

.tool-input,
.tool-textarea {
  background: rgba(0,0,0,0.4);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 3px;
  padding: 8px 10px;
  color: var(--ink);
  font-family: inherit;
  font-size: 12px;
  outline: none;
  transition: border-color 0.15s ease;
  width: 100%;
  min-width: 0;
}
.tool-input.mono { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; }
.tool-input:focus,
.tool-textarea:focus {
  border-color: var(--accent-strong);
}
.tool-textarea { resize: vertical; line-height: 1.5; }

.tool-actions {
  display: flex; gap: 6px; flex-wrap: wrap;
}
.tool-btn {
  background: rgba(0,0,0,0.4);
  border: 1px solid var(--accent-border);
  color: var(--accent-text);
  padding: 6px 12px;
  font-family: inherit;
  font-size: 11px;
  letter-spacing: 0.08em;
  border-radius: 2px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.tool-btn:hover { background: var(--accent-shadow); border-color: var(--accent-strong); }
.tool-btn.ghost { background: transparent; }
.tool-btn.danger {
  color: #ffd9dc;
  border-color: rgba(255,95,109,0.35);
  background: rgba(255,95,109,0.06);
}
.tool-btn.danger:hover { background: rgba(255,95,109,0.12); border-color: #ff5f6d; }

.tool-empty {
  padding: 36px 16px;
  text-align: center;
  color: var(--ink-ghost);
  font-size: 12px;
}

.divlabel-sm {
  font-size: 9.5px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--ink-ghost);
  margin: 10px 14px 2px;
}

/* ── Calendar timeline ─────────────────────────────────── */
.cal-grid {
  padding: 10px 14px;
}
.cal-timeline {
  position: relative;
  border-left: 1px solid rgba(255,255,255,0.08);
  height: 520px;
}
.cal-hour {
  height: 40px;
  border-top: 1px dashed rgba(255,255,255,0.05);
  padding: 2px 0 0 8px;
  font-size: 9.5px;
  color: var(--ink-ghost);
  letter-spacing: 0.08em;
}
.cal-event {
  position: absolute;
  left: 70px;
  right: 12px;
  background: rgba(0,0,0,0.6);
  border: 1px solid rgba(255,255,255,0.1);
  border-left: 2px solid var(--ink-ghost);
  border-radius: 2px;
  padding: 6px 10px;
  font-size: 11px;
  overflow: hidden;
}
.cal-event.accent {
  border-color: var(--accent-border);
  border-left-color: var(--accent-strong);
  background: linear-gradient(90deg, var(--accent-shadow), rgba(0,0,0,0.5));
  box-shadow: 0 0 10px var(--accent-shadow);
}
.cal-event.warn {
  border-left-color: #fb923c;
  background: rgba(251,146,60,0.06);
}
.cal-event.focus {
  outline: 1px dashed var(--accent-strong);
  outline-offset: -3px;
}
.cal-evt-time {
  font-size: 9.5px;
  color: var(--ink-ghost);
  letter-spacing: 0.08em;
}
.cal-evt-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink);
  margin-top: 1px;
}
.cal-evt-sub {
  font-size: 10.5px;
  color: var(--ink-dim);
  margin-top: 1px;
}

/* ── WhatsApp avatars ──────────────────────────────────── */
.avatar {
  width: 26px; height: 26px;
  border-radius: 50%;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  display: grid; place-items: center;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--accent-text);
  letter-spacing: 0.08em;
  flex-shrink: 0;
  position: relative;
}
.avatar.online::after {
  content: "";
  position: absolute;
  bottom: -1px; right: -1px;
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--accent-strong);
  border: 2px solid #04060a;
  box-shadow: 0 0 4px var(--accent-glow);
}

/* ── GitHub ────────────────────────────────────────────── */
.gh-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  padding: 12px 14px 4px;
}
.gh-stat {
  border: 1px solid rgba(255,255,255,0.06);
  background: rgba(0,0,0,0.25);
  padding: 8px 10px;
  border-radius: 2px;
}
.gh-stat .k {
  font-size: 9.5px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--ink-ghost);
}
.gh-stat .v {
  font-size: 16px;
  color: var(--accent-text);
  margin-top: 2px;
}
.gh-tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--ink-ghost);
  padding: 1px 6px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 2px;
  background: rgba(0,0,0,0.4);
  flex-shrink: 0;
}

/* ── Spotify ───────────────────────────────────────────── */
.spt-now {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 16px;
  padding: 16px;
  align-items: center;
}
.spt-cover {
  width: 110px; height: 110px;
  border: 1px solid var(--accent-border);
  background: linear-gradient(135deg, var(--accent-shadow), rgba(0,0,0,0.6));
  border-radius: 2px;
  display: grid; place-items: center;
  position: relative;
  overflow: hidden;
}
.spt-cover::before {
  content: "";
  position: absolute; inset: 0;
  background:
    radial-gradient(circle at 30% 30%, var(--accent-glow), transparent 60%),
    radial-gradient(circle at 70% 70%, rgba(255,255,255,0.05), transparent 50%);
  opacity: 0.7;
}
.spt-cover-inner {
  font-size: 42px;
  color: var(--accent-strong);
  text-shadow: 0 0 20px var(--accent-glow);
  position: relative;
  z-index: 1;
}
.spt-meta { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.spt-track { font-size: 14px; font-weight: 600; color: var(--ink); }
.spt-artist { font-size: 11.5px; color: var(--ink-dim); }
.spt-bar {
  height: 3px;
  background: rgba(255,255,255,0.08);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 4px;
}
.spt-bar-fill {
  height: 100%;
  background: var(--accent-strong);
  box-shadow: 0 0 8px var(--accent-glow);
}
.spt-times {
  display: flex; justify-content: space-between;
  font-size: 10px;
  color: var(--ink-ghost);
  letter-spacing: 0.08em;
}
.spt-controls {
  display: flex; align-items: center; gap: 8px;
  margin-top: 4px;
}
.spt-btn {
  background: transparent;
  border: 1px solid var(--accent-border);
  border-radius: 2px;
  color: var(--accent-text);
  width: 30px; height: 30px;
  display: grid; place-items: center;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.15s ease;
}
.spt-btn:hover { background: var(--accent-shadow); }
.spt-btn.play { width: 38px; height: 38px; background: var(--accent-shadow); font-size: 14px; }
.spt-vol { display: flex; align-items: center; gap: 8px; flex: 1; margin-left: 12px; }
.spt-vol-bar { flex: 1; height: 3px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden; }
.spt-vol-fill { height: 100%; background: var(--accent-strong); }

.mode-mini {
  font-size: 12px;
  color: var(--ink);
  padding: 4px 10px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 2px;
  background: rgba(0,0,0,0.3);
}
.mode-mini.active {
  border-color: var(--accent-strong);
  background: var(--accent-shadow);
  color: var(--accent-text);
}

/* ── Habits ────────────────────────────────────────────── */
.habit-row {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  gap: 10px;
  align-items: center;
  padding: 8px 10px;
  border: 1px solid rgba(255,255,255,0.05);
  border-radius: 3px;
  background: rgba(255,255,255,0.01);
  margin-bottom: 4px;
}
.habit-tick {
  width: 22px; height: 22px;
  border: 1px solid rgba(255,255,255,0.15);
  background: transparent;
  border-radius: 2px;
  cursor: pointer;
  color: var(--accent-strong);
  font-size: 13px;
  display: grid; place-items: center;
  font-weight: 600;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.habit-tick.done {
  background: var(--accent-shadow);
  border-color: var(--accent-strong);
  color: var(--accent-strong);
  text-shadow: 0 0 6px var(--accent-glow);
}
.habit-body { min-width: 0; }
.habit-name { font-size: 12.5px; color: var(--ink); }
.habit-meta {
  font-size: 9.5px;
  color: var(--ink-ghost);
  letter-spacing: 0.08em;
  margin-top: 1px;
}
.habit-history {
  display: flex; gap: 2px;
}
.habit-day {
  width: 8px; height: 14px;
  background: rgba(255,255,255,0.05);
  border-radius: 1px;
}
.habit-day.on { background: var(--accent-strong); box-shadow: 0 0 4px var(--accent-glow); }

.bell-ico, .note-ico {
  width: 18px; height: 18px;
  display: grid; place-items: center;
  font-size: 10px;
  color: var(--accent-text);
  flex-shrink: 0;
}

/* ── News ──────────────────────────────────────────────── */
.news-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px;
  padding: 12px 14px;
}
@media (max-width: 1400px) {
  .news-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 980px) {
  .news-grid { grid-template-columns: 1fr; }
}
.news-feed {
  border: 1px solid rgba(255,255,255,0.06);
  background: rgba(0,0,0,0.3);
  border-radius: 2px;
  padding: 10px;
}
.news-feed-name {
  font-size: 9.5px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--accent-text);
  font-weight: 600;
  padding-bottom: 6px;
  margin-bottom: 6px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.news-items { display: flex; flex-direction: column; gap: 6px; }
.news-item {
  cursor: pointer;
  padding: 6px;
  border-radius: 2px;
  transition: background 0.15s ease;
}
.news-item:hover { background: rgba(255,255,255,0.025); }
.news-title { font-size: 12px; color: var(--ink); line-height: 1.4; }
.news-meta {
  font-size: 10px;
  color: var(--ink-ghost);
  margin-top: 3px;
  letter-spacing: 0.06em;
}

/* ── Operations sub-tabs ──────────────────────────────── */
.ops-tabs {
  display: flex;
  background: rgba(0,0,0,0.4);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 3px;
  padding: 2px;
}
.ops-tab {
  background: transparent;
  border: none;
  color: var(--ink-ghost);
  font-family: inherit;
  font-size: 10.5px;
  letter-spacing: 0.1em;
  padding: 5px 12px;
  cursor: pointer;
  border-radius: 2px;
  transition: background 0.15s ease, color 0.15s ease;
}
.ops-tab:hover { color: var(--ink); }
.ops-tab.active {
  background: var(--accent-shadow);
  color: var(--accent-text);
}

/* ── Pomodoro ──────────────────────────────────────────── */
.pom-card {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 24px;
  padding: 20px 16px;
  align-items: center;
}
.pom-ring { width: 160px; height: 160px; }
.pom-ring svg { width: 100%; height: 100%; }
.pom-meta { display: flex; flex-direction: column; gap: 12px; }
.pom-meta .k {
  font-size: 9.5px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--ink-ghost);
}
.pom-meta .v {
  font-size: 14px;
  color: var(--ink);
  margin-top: 2px;
}

/* ── Clipboard ─────────────────────────────────────────── */
.clip-text {
  font-size: 11.5px;
  color: var(--accent-text);
  background: rgba(0,0,0,0.4);
  padding: 4px 8px;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 380px;
  display: inline-block;
}

/* ── Planner ───────────────────────────────────────────── */
.planner-chain {
  padding: 8px 14px 4px;
  position: relative;
}
.plan-step {
  display: grid;
  grid-template-columns: 40px 1fr;
  gap: 12px;
  padding: 10px 0;
  position: relative;
}
.plan-num {
  width: 32px; height: 32px;
  border-radius: 2px;
  border: 1px solid var(--accent-border);
  background: rgba(0,0,0,0.4);
  display: grid; place-items: center;
  color: var(--accent-text);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0;
  z-index: 2;
  position: relative;
}
.plan-num.med { color: #fdba74; border-color: rgba(251,146,60,0.35); }
.plan-num.high { color: #fda4af; border-color: rgba(255,95,109,0.35); }
.plan-body { padding-top: 4px; }
.plan-title { font-size: 12.5px; color: var(--ink); }
.plan-meta {
  font-size: 10px;
  color: var(--ink-ghost);
  margin-top: 3px;
  letter-spacing: 0.06em;
}
.risk-low { color: var(--accent-strong); }
.risk-med { color: #fdba74; }
.risk-high { color: #fda4af; }
.plan-line {
  position: absolute;
  left: 20px;
  top: 44px;
  bottom: -6px;
  width: 1px;
  background: linear-gradient(to bottom, var(--accent-border), transparent);
}

/* ── Layout: spread tool panel across center bottom ───── */
.tools-wrap { grid-column: 1 / -1; }
@media (min-width: 1180px) {
  .shell.with-tools {
    grid-template-areas:
      "left center right"
      "left tools  right";
    grid-template-rows: auto 1fr;
  }
  .shell.with-tools > .col.left   { grid-area: left; }
  .shell.with-tools > .col.center { grid-area: center; }
  .shell.with-tools > .col.right  { grid-area: right; }
  .shell.with-tools > .tools-wrap { grid-area: tools; }
}

// tweaks-panel.jsx
// Reusable Tweaks shell + form-control helpers.
//
// Owns the host protocol (listens for __activate_edit_mode / __deactivate_edit_mode,
// posts __edit_mode_available / __edit_mode_set_keys / __edit_mode_dismissed) so
// individual prototypes don't re-roll it. Ships a consistent set of controls so you
// don't hand-draw <input type="range">, segmented radios, steppers, etc.
//
// Usage (in an HTML file that loads React + Babel):
//
//   const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
//     "primaryColor": "#D97757",
//     "palette": ["#D97757", "#29261b", "#f6f4ef"],
//     "fontSize": 16,
//     "density": "regular",
//     "dark": false
//   }/*EDITMODE-END*/;
//
//   function App() {
//     const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
//     return (
//       <div style={{ fontSize: t.fontSize, color: t.primaryColor }}>
//         Hello
//         <TweaksPanel>
//           <TweakSection label="Typography" />
//           <TweakSlider label="Font size" value={t.fontSize} min={10} max={32} unit="px"
//                        onChange={(v) => setTweak('fontSize', v)} />
//           <TweakRadio  label="Density" value={t.density}
//                        options={['compact', 'regular', 'comfy']}
//                        onChange={(v) => setTweak('density', v)} />
//           <TweakSection label="Theme" />
//           <TweakColor  label="Primary" value={t.primaryColor}
//                        options={['#D97757', '#2A6FDB', '#1F8A5B', '#7A5AE0']}
//                        onChange={(v) => setTweak('primaryColor', v)} />
//           <TweakColor  label="Palette" value={t.palette}
//                        options={[['#D97757', '#29261b', '#f6f4ef'],
//                                  ['#475569', '#0f172a', '#f1f5f9']]}
//                        onChange={(v) => setTweak('palette', v)} />
//           <TweakToggle label="Dark mode" value={t.dark}
//                        onChange={(v) => setTweak('dark', v)} />
//         </TweaksPanel>
//       </div>
//     );
//   }
//
// ─────────────────────────────────────────────────────────────────────────────

const __TWEAKS_STYLE = `
  .twk-panel{position:fixed;right:16px;bottom:16px;z-index:2147483646;width:280px;
    max-height:calc(100vh - 32px);display:flex;flex-direction:column;
    transform:scale(var(--dc-inv-zoom,1));transform-origin:bottom right;
    background:rgba(250,249,247,.78);color:#29261b;
    -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
    border:.5px solid rgba(255,255,255,.6);border-radius:14px;
    box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 12px 40px rgba(0,0,0,.18);
    font:11.5px/1.4 ui-sans-serif,system-ui,-apple-system,sans-serif;overflow:hidden}
  .twk-hd{display:flex;align-items:center;justify-content:space-between;
    padding:10px 8px 10px 14px;cursor:move;user-select:none}
  .twk-hd b{font-size:12px;font-weight:600;letter-spacing:.01em}
  .twk-x{appearance:none;border:0;background:transparent;color:rgba(41,38,27,.55);
    width:22px;height:22px;border-radius:6px;cursor:default;font-size:13px;line-height:1}
  .twk-x:hover{background:rgba(0,0,0,.06);color:#29261b}
  .twk-body{padding:2px 14px 14px;display:flex;flex-direction:column;gap:10px;
    overflow-y:auto;overflow-x:hidden;min-height:0;
    scrollbar-width:thin;scrollbar-color:rgba(0,0,0,.15) transparent}
  .twk-body::-webkit-scrollbar{width:8px}
  .twk-body::-webkit-scrollbar-track{background:transparent;margin:2px}
  .twk-body::-webkit-scrollbar-thumb{background:rgba(0,0,0,.15);border-radius:4px;
    border:2px solid transparent;background-clip:content-box}
  .twk-body::-webkit-scrollbar-thumb:hover{background:rgba(0,0,0,.25);
    border:2px solid transparent;background-clip:content-box}
  .twk-row{display:flex;flex-direction:column;gap:5px}
  .twk-row-h{flex-direction:row;align-items:center;justify-content:space-between;gap:10px}
  .twk-lbl{display:flex;justify-content:space-between;align-items:baseline;
    color:rgba(41,38,27,.72)}
  .twk-lbl>span:first-child{font-weight:500}
  .twk-val{color:rgba(41,38,27,.5);font-variant-numeric:tabular-nums}

  .twk-sect{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
    color:rgba(41,38,27,.45);padding:10px 0 0}
  .twk-sect:first-child{padding-top:0}

  .twk-field{appearance:none;box-sizing:border-box;width:100%;min-width:0;height:26px;padding:0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;
    background:rgba(255,255,255,.6);color:inherit;font:inherit;outline:none}
  .twk-field:focus{border-color:rgba(0,0,0,.25);background:rgba(255,255,255,.85)}
  select.twk-field{padding-right:22px;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='rgba(0,0,0,.5)' d='M0 0h10L5 6z'/></svg>");
    background-repeat:no-repeat;background-position:right 8px center}

  .twk-slider{appearance:none;-webkit-appearance:none;width:100%;height:4px;margin:6px 0;
    border-radius:999px;background:rgba(0,0,0,.12);outline:none}
  .twk-slider::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;
    width:14px;height:14px;border-radius:50%;background:#fff;
    border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}
  .twk-slider::-moz-range-thumb{width:14px;height:14px;border-radius:50%;
    background:#fff;border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}

  .twk-seg{position:relative;display:flex;padding:2px;border-radius:8px;
    background:rgba(0,0,0,.06);user-select:none}
  .twk-seg-thumb{position:absolute;top:2px;bottom:2px;border-radius:6px;
    background:rgba(255,255,255,.9);box-shadow:0 1px 2px rgba(0,0,0,.12);
    transition:left .15s cubic-bezier(.3,.7,.4,1),width .15s}
  .twk-seg.dragging .twk-seg-thumb{transition:none}
  .twk-seg button{appearance:none;position:relative;z-index:1;flex:1;border:0;
    background:transparent;color:inherit;font:inherit;font-weight:500;min-height:22px;
    border-radius:6px;cursor:default;padding:4px 6px;line-height:1.2;
    overflow-wrap:anywhere}

  .twk-toggle{position:relative;width:32px;height:18px;border:0;border-radius:999px;
    background:rgba(0,0,0,.15);transition:background .15s;cursor:default;padding:0}
  .twk-toggle[data-on="1"]{background:#34c759}
  .twk-toggle i{position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;
    background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform .15s}
  .twk-toggle[data-on="1"] i{transform:translateX(14px)}

  .twk-num{display:flex;align-items:center;box-sizing:border-box;min-width:0;height:26px;padding:0 0 0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;background:rgba(255,255,255,.6)}
  .twk-num-lbl{font-weight:500;color:rgba(41,38,27,.6);cursor:ew-resize;
    user-select:none;padding-right:8px}
  .twk-num input{flex:1;min-width:0;height:100%;border:0;background:transparent;
    font:inherit;font-variant-numeric:tabular-nums;text-align:right;padding:0 8px 0 0;
    outline:none;color:inherit;-moz-appearance:textfield}
  .twk-num input::-webkit-inner-spin-button,.twk-num input::-webkit-outer-spin-button{
    -webkit-appearance:none;margin:0}
  .twk-num-unit{padding-right:8px;color:rgba(41,38,27,.45)}

  .twk-btn{appearance:none;height:26px;padding:0 12px;border:0;border-radius:7px;
    background:rgba(0,0,0,.78);color:#fff;font:inherit;font-weight:500;cursor:default}
  .twk-btn:hover{background:rgba(0,0,0,.88)}
  .twk-btn.secondary{background:rgba(0,0,0,.06);color:inherit}
  .twk-btn.secondary:hover{background:rgba(0,0,0,.1)}

  .twk-swatch{appearance:none;-webkit-appearance:none;width:56px;height:22px;
    border:.5px solid rgba(0,0,0,.1);border-radius:6px;padding:0;cursor:default;
    background:transparent;flex-shrink:0}
  .twk-swatch::-webkit-color-swatch-wrapper{padding:0}
  .twk-swatch::-webkit-color-swatch{border:0;border-radius:5.5px}
  .twk-swatch::-moz-color-swatch{border:0;border-radius:5.5px}

  .twk-chips{display:flex;gap:6px}
  .twk-chip{position:relative;appearance:none;flex:1;min-width:0;height:46px;
    padding:0;border:0;border-radius:6px;overflow:hidden;cursor:default;
    box-shadow:0 0 0 .5px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.06);
    transition:transform .12s cubic-bezier(.3,.7,.4,1),box-shadow .12s}
  .twk-chip:hover{transform:translateY(-1px);
    box-shadow:0 0 0 .5px rgba(0,0,0,.18),0 4px 10px rgba(0,0,0,.12)}
  .twk-chip[data-on="1"]{box-shadow:0 0 0 1.5px rgba(0,0,0,.85),
    0 2px 6px rgba(0,0,0,.15)}
  .twk-chip>span{position:absolute;top:0;bottom:0;right:0;width:34%;
    display:flex;flex-direction:column;box-shadow:-1px 0 0 rgba(0,0,0,.1)}
  .twk-chip>span>i{flex:1;box-shadow:0 -1px 0 rgba(0,0,0,.1)}
  .twk-chip>span>i:first-child{box-shadow:none}
  .twk-chip svg{position:absolute;top:6px;left:6px;width:13px;height:13px;
    filter:drop-shadow(0 1px 1px rgba(0,0,0,.3))}
`;

// ── useTweaks ───────────────────────────────────────────────────────────────
// Single source of truth for tweak values. setTweak persists via the host
// (__edit_mode_set_keys → host rewrites the EDITMODE block on disk).
function useTweaks(defaults) {
  const [values, setValues] = React.useState(defaults);
  // Accepts either setTweak('key', value) or setTweak({ key: value, ... }) so a
  // useState-style call doesn't write a "[object Object]" key into the persisted
  // JSON block.
  const setTweak = React.useCallback((keyOrEdits, val) => {
    const edits = typeof keyOrEdits === 'object' && keyOrEdits !== null
      ? keyOrEdits : { [keyOrEdits]: val };
    setValues((prev) => ({ ...prev, ...edits }));
    window.parent.postMessage({ type: '__edit_mode_set_keys', edits }, '*');
    // Same-window signal so in-page listeners (deck-stage rail thumbnails)
    // can react — the parent message only reaches the host, not peers.
    window.dispatchEvent(new CustomEvent('tweakchange', { detail: edits }));
  }, []);
  return [values, setTweak];
}

// ── TweaksPanel ─────────────────────────────────────────────────────────────
// Floating shell. Registers the protocol listener BEFORE announcing
// availability — if the announce ran first, the host's activate could land
// before our handler exists and the toolbar toggle would silently no-op.
// The close button posts __edit_mode_dismissed so the host's toolbar toggle
// flips off in lockstep; the host echoes __deactivate_edit_mode back which
// is what actually hides the panel.
function TweaksPanel({ title = 'Tweaks', noDeckControls = false, children }) {
  const [open, setOpen] = React.useState(false);
  const dragRef = React.useRef(null);
  // Auto-inject a rail toggle when a <deck-stage> is on the page. The
  // toggle drives the deck's per-viewer _railVisible via window message;
  // state is mirrored from the same localStorage key the deck reads so
  // the control reflects reality across reloads. The mechanism is the
  // message — authors who want custom placement can post it directly
  // and pass noDeckControls to suppress this one.
  const hasDeckStage = React.useMemo(
    () => typeof document !== 'undefined' && !!document.querySelector('deck-stage'),
    [],
  );
  // deck-stage enables its rail in connectedCallback, but this panel can
  // mount before that element has upgraded. The initial read catches the
  // common case; the listener covers mounting first. (Older deck-stage.js
  // copies still wait for the host's __omelette_rail_enabled postMessage —
  // same listener handles those.)
  const [railEnabled, setRailEnabled] = React.useState(
    () => hasDeckStage && !!document.querySelector('deck-stage')?._railEnabled,
  );
  React.useEffect(() => {
    if (!hasDeckStage || railEnabled) return undefined;
    const onMsg = (e) => {
      if (e.data && e.data.type === '__omelette_rail_enabled') setRailEnabled(true);
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, [hasDeckStage, railEnabled]);
  const [railVisible, setRailVisible] = React.useState(() => {
    try { return localStorage.getItem('deck-stage.railVisible') !== '0'; } catch (e) { return true; }
  });
  const toggleRail = (on) => {
    setRailVisible(on);
    window.postMessage({ type: '__deck_rail_visible', on }, '*');
  };
  const offsetRef = React.useRef({ x: 16, y: 16 });
  const PAD = 16;

  const clampToViewport = React.useCallback(() => {
    const panel = dragRef.current;
    if (!panel) return;
    const w = panel.offsetWidth, h = panel.offsetHeight;
    const maxRight = Math.max(PAD, window.innerWidth - w - PAD);
    const maxBottom = Math.max(PAD, window.innerHeight - h - PAD);
    offsetRef.current = {
      x: Math.min(maxRight, Math.max(PAD, offsetRef.current.x)),
      y: Math.min(maxBottom, Math.max(PAD, offsetRef.current.y)),
    };
    panel.style.right = offsetRef.current.x + 'px';
    panel.style.bottom = offsetRef.current.y + 'px';
  }, []);

  React.useEffect(() => {
    if (!open) return;
    clampToViewport();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', clampToViewport);
      return () => window.removeEventListener('resize', clampToViewport);
    }
    const ro = new ResizeObserver(clampToViewport);
    ro.observe(document.documentElement);
    return () => ro.disconnect();
  }, [open, clampToViewport]);

  React.useEffect(() => {
    const onMsg = (e) => {
      const t = e?.data?.type;
      if (t === '__activate_edit_mode') setOpen(true);
      else if (t === '__deactivate_edit_mode') setOpen(false);
    };
    window.addEventListener('message', onMsg);
    window.parent.postMessage({ type: '__edit_mode_available' }, '*');
    return () => window.removeEventListener('message', onMsg);
  }, []);

  const dismiss = () => {
    setOpen(false);
    window.parent.postMessage({ type: '__edit_mode_dismissed' }, '*');
  };

  const onDragStart = (e) => {
    const panel = dragRef.current;
    if (!panel) return;
    const r = panel.getBoundingClientRect();
    const sx = e.clientX, sy = e.clientY;
    const startRight = window.innerWidth - r.right;
    const startBottom = window.innerHeight - r.bottom;
    const move = (ev) => {
      offsetRef.current = {
        x: startRight - (ev.clientX - sx),
        y: startBottom - (ev.clientY - sy),
      };
      clampToViewport();
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  };

  if (!open) return null;
  return (
    <>
      <style>{__TWEAKS_STYLE}</style>
      <div ref={dragRef} className="twk-panel" data-noncommentable=""
           style={{ right: offsetRef.current.x, bottom: offsetRef.current.y }}>
        <div className="twk-hd" onMouseDown={onDragStart}>
          <b>{title}</b>
          <button className="twk-x" aria-label="Close tweaks"
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={dismiss}>✕</button>
        </div>
        <div className="twk-body">
          {children}
          {hasDeckStage && railEnabled && !noDeckControls && (
            <TweakSection label="Deck">
              <TweakToggle label="Thumbnail rail" value={railVisible} onChange={toggleRail} />
            </TweakSection>
          )}
        </div>
      </div>
    </>
  );
}

// ── Layout helpers ──────────────────────────────────────────────────────────

function TweakSection({ label, children }) {
  return (
    <>
      <div className="twk-sect">{label}</div>
      {children}
    </>
  );
}

function TweakRow({ label, value, children, inline = false }) {
  return (
    <div className={inline ? 'twk-row twk-row-h' : 'twk-row'}>
      <div className="twk-lbl">
        <span>{label}</span>
        {value != null && <span className="twk-val">{value}</span>}
      </div>
      {children}
    </div>
  );
}

// ── Controls ────────────────────────────────────────────────────────────────

function TweakSlider({ label, value, min = 0, max = 100, step = 1, unit = '', onChange }) {
  return (
    <TweakRow label={label} value={`${value}${unit}`}>
      <input type="range" className="twk-slider" min={min} max={max} step={step}
             value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </TweakRow>
  );
}

function TweakToggle({ label, value, onChange }) {
  return (
    <div className="twk-row twk-row-h">
      <div className="twk-lbl"><span>{label}</span></div>
      <button type="button" className="twk-toggle" data-on={value ? '1' : '0'}
              role="switch" aria-checked={!!value}
              onClick={() => onChange(!value)}><i /></button>
    </div>
  );
}

function TweakRadio({ label, value, options, onChange }) {
  const trackRef = React.useRef(null);
  const [dragging, setDragging] = React.useState(false);
  // The active value is read by pointer-move handlers attached for the lifetime
  // of a drag — ref it so a stale closure doesn't fire onChange for every move.
  const valueRef = React.useRef(value);
  valueRef.current = value;

  // Segments wrap mid-word once per-segment width runs out. The track is
  // ~248px (280 panel − 28 body pad − 4 seg pad), each button loses 12px
  // to its own padding, and 11.5px system-ui averages ~6.3px/char — so 2
  // options fit ~16 chars each, 3 fit ~10. Past that (or >3 options), fall
  // back to a dropdown rather than wrap.
  const labelLen = (o) => String(typeof o === 'object' ? o.label : o).length;
  const maxLen = options.reduce((m, o) => Math.max(m, labelLen(o)), 0);
  const fitsAsSegments = maxLen <= ({ 2: 16, 3: 10 }[options.length] ?? 0);
  if (!fitsAsSegments) {
    // <select> emits strings — map back to the original option value so the
    // fallback stays type-preserving (numbers, booleans) like the segment path.
    const resolve = (s) => {
      const m = options.find((o) => String(typeof o === 'object' ? o.value : o) === s);
      return m === undefined ? s : typeof m === 'object' ? m.value : m;
    };
    return <TweakSelect label={label} value={value} options={options}
                        onChange={(s) => onChange(resolve(s))} />;
  }
  const opts = options.map((o) => (typeof o === 'object' ? o : { value: o, label: o }));
  const idx = Math.max(0, opts.findIndex((o) => o.value === value));
  const n = opts.length;

  const segAt = (clientX) => {
    const r = trackRef.current.getBoundingClientRect();
    const inner = r.width - 4;
    const i = Math.floor(((clientX - r.left - 2) / inner) * n);
    return opts[Math.max(0, Math.min(n - 1, i))].value;
  };

  const onPointerDown = (e) => {
    setDragging(true);
    const v0 = segAt(e.clientX);
    if (v0 !== valueRef.current) onChange(v0);
    const move = (ev) => {
      if (!trackRef.current) return;
      const v = segAt(ev.clientX);
      if (v !== valueRef.current) onChange(v);
    };
    const up = () => {
      setDragging(false);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  return (
    <TweakRow label={label}>
      <div ref={trackRef} role="radiogroup" onPointerDown={onPointerDown}
           className={dragging ? 'twk-seg dragging' : 'twk-seg'}>
        <div className="twk-seg-thumb"
             style={{ left: `calc(2px + ${idx} * (100% - 4px) / ${n})`,
                      width: `calc((100% - 4px) / ${n})` }} />
        {opts.map((o) => (
          <button key={o.value} type="button" role="radio" aria-checked={o.value === value}>
            {o.label}
          </button>
        ))}
      </div>
    </TweakRow>
  );
}

function TweakSelect({ label, value, options, onChange }) {
  return (
    <TweakRow label={label}>
      <select className="twk-field" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => {
          const v = typeof o === 'object' ? o.value : o;
          const l = typeof o === 'object' ? o.label : o;
          return <option key={v} value={v}>{l}</option>;
        })}
      </select>
    </TweakRow>
  );
}

function TweakText({ label, value, placeholder, onChange }) {
  return (
    <TweakRow label={label}>
      <input className="twk-field" type="text" value={value} placeholder={placeholder}
             onChange={(e) => onChange(e.target.value)} />
    </TweakRow>
  );
}

function TweakNumber({ label, value, min, max, step = 1, unit = '', onChange }) {
  const clamp = (n) => {
    if (min != null && n < min) return min;
    if (max != null && n > max) return max;
    return n;
  };
  const startRef = React.useRef({ x: 0, val: 0 });
  const onScrubStart = (e) => {
    e.preventDefault();
    startRef.current = { x: e.clientX, val: value };
    const decimals = (String(step).split('.')[1] || '').length;
    const move = (ev) => {
      const dx = ev.clientX - startRef.current.x;
      const raw = startRef.current.val + dx * step;
      const snapped = Math.round(raw / step) * step;
      onChange(clamp(Number(snapped.toFixed(decimals))));
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  return (
    <div className="twk-num">
      <span className="twk-num-lbl" onPointerDown={onScrubStart}>{label}</span>
      <input type="number" value={value} min={min} max={max} step={step}
             onChange={(e) => onChange(clamp(Number(e.target.value)))} />
      {unit && <span className="twk-num-unit">{unit}</span>}
    </div>
  );
}

// Relative-luminance contrast pick — checkmarks drawn over a swatch need to
// read on both #111 and #fafafa without per-option configuration. Hex input
// only (#rgb / #rrggbb); named or rgb()/hsl() colors fall through to "light".
function __twkIsLight(hex) {
  const h = String(hex).replace('#', '');
  const x = h.length === 3 ? h.replace(/./g, (c) => c + c) : h.padEnd(6, '0');
  const n = parseInt(x.slice(0, 6), 16);
  if (Number.isNaN(n)) return true;
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return r * 299 + g * 587 + b * 114 > 148000;
}

const __TwkCheck = ({ light }) => (
  <svg viewBox="0 0 14 14" aria-hidden="true">
    <path d="M3 7.2 5.8 10 11 4.2" fill="none" strokeWidth="2.2"
          strokeLinecap="round" strokeLinejoin="round"
          stroke={light ? 'rgba(0,0,0,.78)' : '#fff'} />
  </svg>
);

// TweakColor — curated color/palette picker. Each option is either a single
// hex string or an array of 1-5 hex strings; the card adapts — a lone color
// renders solid, a palette renders colors[0] as the hero (left ~2/3) with the
// rest stacked in a sharp column on the right. onChange emits the
// option in the shape it was passed (string stays string, array stays array).
// Without options it falls back to the native color input for back-compat.
function TweakColor({ label, value, options, onChange }) {
  if (!options || !options.length) {
    return (
      <div className="twk-row twk-row-h">
        <div className="twk-lbl"><span>{label}</span></div>
        <input type="color" className="twk-swatch" value={value}
               onChange={(e) => onChange(e.target.value)} />
      </div>
    );
  }
  // Native <input type=color> emits lowercase hex per the HTML spec, so
  // compare case-insensitively. String() guards JSON.stringify(undefined),
  // which returns the primitive undefined (no .toLowerCase).
  const key = (o) => String(JSON.stringify(o)).toLowerCase();
  const cur = key(value);
  return (
    <TweakRow label={label}>
      <div className="twk-chips" role="radiogroup">
        {options.map((o, i) => {
          const colors = Array.isArray(o) ? o : [o];
          const [hero, ...rest] = colors;
          const sup = rest.slice(0, 4);
          const on = key(o) === cur;
          return (
            <button key={i} type="button" className="twk-chip" role="radio"
                    aria-checked={on} data-on={on ? '1' : '0'}
                    aria-label={colors.join(', ')} title={colors.join(' · ')}
                    style={{ background: hero }}
                    onClick={() => onChange(o)}>
              {sup.length > 0 && (
                <span>
                  {sup.map((c, j) => <i key={j} style={{ background: c }} />)}
                </span>
              )}
              {on && <__TwkCheck light={__twkIsLight(hero)} />}
            </button>
          );
        })}
      </div>
    </TweakRow>
  );
}

function TweakButton({ label, onClick, secondary = false }) {
  return (
    <button type="button" className={secondary ? 'twk-btn secondary' : 'twk-btn'}
            onClick={onClick}>{label}</button>
  );
}

Object.assign(window, {
  useTweaks, TweaksPanel, TweakSection, TweakRow,
  TweakSlider, TweakToggle, TweakRadio, TweakSelect,
  TweakText, TweakNumber, TweakColor, TweakButton,
});
