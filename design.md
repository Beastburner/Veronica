---
name: VERONICA Command Center
description: A JARVIS-grade personal AI operating system for one operator at a time.
colors:
  arc-light: "#38e8ff"
  ambercore: "#ffd166"
  mode-veronica: "#b284ff"
  plasma-red: "#ff5f6d"
  plasma-alert: "#ff3f81"
  void-deep: "#04060a"
  void-mid: "#0d1118"
  ink-primary: "#eefbff"
  ink-accent: "#d6f7ff"
  ink-dim: "#94a3b8"
  ink-ghost: "#475569"
typography:
  display:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontSize: "clamp(1.5rem, 3vw, 1.875rem)"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "normal"
  headline:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "normal"
  title:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "normal"
  body:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  label:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0.18em"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "0.6875rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
rounded:
  sm: "4px"
  md: "8px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  button-action:
    backgroundColor: "{colors.arc-light}"
    textColor: "{colors.void-deep}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
  button-action-hover:
    backgroundColor: "{colors.ink-accent}"
    textColor: "{colors.void-deep}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-accent}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  button-danger:
    backgroundColor: "transparent"
    textColor: "#ffd9dc"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  hud-panel:
    backgroundColor: "{colors.void-deep}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.md}"
    padding: "16px"
  input-command:
    backgroundColor: "{colors.void-deep}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  tab-active:
    backgroundColor: "{colors.arc-light}"
    textColor: "{colors.ink-accent}"
    rounded: "{rounded.sm}"
    padding: "6px 12px"
---

# Design System: VERONICA Command Center

## 1. Overview

**Creative North Star: "The Reactor Core"**

VERONICA is hardened kit that happens to be beautiful. Every surface is a control surface. Every glow is functional heat. The interface does not perform futurism — it performs readiness. One operator, one command center, every signal visible at a glance. The aesthetic emerges from purpose: the glow exists because the system is live, not because the designer wanted it to feel futuristic.

The system runs in four modal states — JARVIS (arc-light cyan), FRIDAY (ambercore gold), VERONICA (soft purple), SENTINEL (plasma red) — each representing a distinct cognitive posture. Color is mode signal. The accent at any given moment tells the operator which version of the AI they are addressing and what kind of work they are doing. Flood the UI with color and it stops being a signal. Ration it, and every lit element means something.

Space Grotesk keeps text sharp and legible on dark backgrounds without veering clinical. JetBrains Mono anchors terminal-adjacent surfaces. The pairing reads as precision instrument, not developer tool. Against a near-black void with fractional blue undertones, the type reads as part of the system, not printed on top of it.

**Key Characteristics:**
- Dark-first: optimized for a single operator at a monitor in low ambient light
- Functional glow: arc-light appears only on active, interactive, or live elements
- Four-mode personality: accent shifts with cognitive mode; everything else stays constant
- Kinetic precision: motion confirms state changes, it does not choreograph entrances
- No hierarchy confusion: scale and weight contrast are the only hierarchy tools; color is not used for hierarchy inside a mode

## 2. Colors: The Reactor Palette

Four modal accents over a near-black void. Color is mode signal, not decoration.

### Primary
- **Arc Light** (`#38e8ff`, oklch ~88% 0.12 200): The JARVIS default accent. Applied to active borders, ambient glows, interactive surface tints, and status indicators in JARVIS mode. The system's operational heartbeat — never used decoratively. If it glows, something is live.

### Secondary
- **Ambercore** (`#ffd166`, oklch ~89% 0.14 85): FRIDAY mode accent. Warm productivity signal — planning, tasks, calendar. Same structural role as Arc Light but shifts the emotional register toward focused, deliberate work.
- **Mode Veronica** (`#b284ff`, oklch ~72% 0.20 290): VERONICA mode accent. Problem-response and deep-reasoning posture. The cooler purple suggests depth of thought over speed of action.
- **Plasma Red** (`#ff5f6d`, oklch ~65% 0.22 18): SENTINEL mode accent. Threat monitoring and security posture. The only color in the system that reads as danger without additional context.

### Tertiary
- **Plasma Alert** (`#ff3f81`, oklch ~60% 0.25 350): Error states, destructive action warnings, alert banners. Not a mode color — a semantic signal that cuts across all modes.

### Neutral
- **Void Deep** (`#04060a`): Base background. Tinted fractionally toward the arc-light hue (chroma ~0.005) so it never reads as pure black at close range.
- **Void Mid** (`#0d1118`): Surface and mid-layer background, used in gradients and non-glass panel fills.
- **Ink Primary** (`#eefbff`): Primary body text. Faint cyan undertone keeps it from reading as white paper on a black screen.
- **Ink Accent** (`#d6f7ff`): JARVIS mode label text — panel headers, active tab labels, mode-indicator copy.
- **Ink Dim** (`#94a3b8`): Secondary text, timestamps, metadata.
- **Ink Ghost** (`#475569`): Placeholder text, disabled states, decorative dividers.

### Named Rules
**The Mode Signal Rule.** The active modal accent must appear on at most 10% of the screen surface at any time. Its rarity is what makes it readable as a signal. Flooding the UI with arc-light means it stops meaning "live" and starts meaning "decorator."

**The One Danger Color Rule.** Plasma Alert (`#ff3f81`) is reserved strictly for error states, destructive confirmations, and threat alerts. It does not appear in branding, decorative accents, or hover states. When you see it, something requires attention.

## 3. Typography

**Display/UI Font:** Space Grotesk (weights 300-700, Google Fonts variable)
**Mono/Terminal Font:** JetBrains Mono (weights 300-500, Google Fonts variable)

**Character:** Space Grotesk is geometric but not cold. Its slightly unusual letterforms — the curved g, open terminals — give the UI a considered feel without telegraphing "startup landing page." JetBrains Mono carries technical surfaces with high legibility at small sizes. The pairing lands between mission control and personal instrument.

### Hierarchy
- **Display** (600 weight, clamp 1.5-1.875rem, 1.2 line-height): Section headers, major panel names. One per logical surface area — not used inside sub-panels.
- **Headline** (600, 1.25rem, 1.3 line-height): Panel section titles, mode name in header bar.
- **Title** (600, 0.875rem, 1.4 line-height): Card headers, list item labels, tab labels. The primary workhorse step.
- **Body** (400, 0.875rem, 1.6 line-height): Message content, briefing text, descriptions. Cap at 65ch.
- **Label** (400, 0.75rem, tracking 0.18em, UPPERCASE): Mode indicators, section identifiers, status tags, COMMANDER/VERONICA message role markers. The tracking makes these legible at tiny sizes and gives the UI its classified-document aesthetic.
- **Mono** (JetBrains Mono 400, 0.6875rem, 1.6 line-height): Code blocks, terminal output, technical IDs, latency readouts. Exclusively for machine-generated or computer-formatted content.

### Named Rules
**The UPPERCASE Label Rule.** Labels that identify system state, mode, or category are set in uppercase with `letter-spacing: 0.18em`. This signals "system annotation" versus "human content." Never apply uppercase tracking to body copy or interactive text.

**The Mono Quarantine Rule.** JetBrains Mono is reserved for genuinely technical content: code, IDs, latency values, console output. Using it for decorative purposes — timestamps, flavor text — dilutes the signal.

## 4. Elevation

This system uses glow-based tonal elevation, not shadow stacking. Depth is expressed through light emission, not shadow casting. A panel floats because it emits arc-light along its border, not because it has a directional drop shadow.

The two elevation tools are: (1) **Border glow** — `var(--accent-border)` at 22% opacity, the baseline "surface exists here" signal on all `.hud-panel` elements. (2) **Ambient bloom** — `0 0 28px var(--accent-glow)`, the floating signal, applied via box-shadow. Intensity scales with mode.

**The Flat Interior Rule.** Inside a panel, there is no elevation. Elements within a `.hud-panel` do not have box shadows or glow rings. Nested glow compounds into visual noise. Internal structure uses only background tints (`rgba(0,0,0,0.2)`, `rgba(255,255,255,0.03)`) and border hairlines (`rgba(255,255,255,0.1)`).

### Shadow Vocabulary
- **Panel ambient** (`0 0 28px rgba(56,232,255,0.45), inset 0 0 20px rgba(5,10,16,0.5)`): The signature `.hud-panel` elevation. Outward bloom places the panel in space; inset shadow deepens the interior.
- **Core bloom** (`0 0 80px rgba(56,232,255,0.45)`): Reserved exclusively for the ArcCore visualization orb. One element in the entire UI uses this. Not a component pattern.
- **Reactor pulse** (animated: cycles panel ambient to core bloom at 2.4s ease-in-out): Active mode indicator. Applied only to the selected mode button.

### Named Rules
**The No Layered Shadow Rule.** Never stack multiple box-shadows to simulate material depth (offset-x, offset-y, spread). The only shadows in this system are zero-offset radial blooms. If you find yourself writing `box-shadow: 4px 8px 16px rgba(...)`, you are in the wrong register.

## 5. Components

### HUD Panel (Signature Component)
The core container of the system. Every panel, section, and data surface lives inside a `.hud-panel`. Character: a piece of machined equipment with clean edges and a live interior glow.

- **Shape:** Gently rounded (8px, `rounded-lg`) — enough to feel considered, not enough to feel consumer
- **Background:** `rgba(5,10,16,0.72)` with `backdrop-filter: blur(18px)` — translucency that implies depth without decorative glass
- **Border:** 1px `var(--accent-border)` at 22% opacity
- **Ambient glow:** `0 0 28px var(--accent-glow)` outward bloom + inset depth shadow
- **Corner Brackets:** `::before` and `::after` pseudo-elements place 12px L-shaped bracket marks at top-left and bottom-right corners (2px, accent-dim color). The system's most distinctive visual signature. Applied only to `.hud-panel` — never to child elements.
- **Active state:** `reactor-pulse` animation adds a 2.4s breathing glow cycle to the selected mode button

### Buttons
Character: armed and waiting. Crisp response. No bounce, no elastic.

- **Action Button:** 10-15% accent opacity fill, accent-30% border, ink-accent text. Padding `px-3 py-1.5` (small) to `px-5 py-3` (standard). Transitions to 20-25% opacity on hover at 0.2s ease-out.
- **Ghost Button:** Transparent background, accent-30% border, ink-accent text. Secondary actions within panels.
- **Danger Button:** `border-pink-300/30 text-pink-200` — destructive actions (delete, reset). No fill background. Hover: `bg-pink-400/10`.
- **Disabled:** 50% opacity, `cursor-not-allowed`. No other visual change.

### Inputs
- **Style:** `border border-[var(--accent)]/20 bg-black/30` — near-invisible at rest
- **Focus:** Border snaps to full `--accent-strong` intensity. No glow ring, no background shift. The border does all the work.
- **Placeholder:** Ink Ghost (`#475569`) — functionally invisible until focused
- **Textarea:** Same as input; always `resize-none`

### Tab Bar
- **Container:** `border border-white/10 bg-black/30 rounded-lg p-1` — inset strip
- **Inactive:** `text-slate-400`, no background
- **Active:** `bg-[var(--accent)]/20 border border-[var(--accent)]/30 text-[var(--accent-text)]`
- **Overflow:** Horizontal scroll (`overflow-x-auto`) on narrow viewports. Tabs never wrap.

### Mode Selector Buttons
Four personality buttons in the left panel. Active selection drives the entire UI's color mode.

- **Inactive:** `border-white/10 bg-white/[0.03]` — recedes completely into the background
- **Active:** `border-[var(--accent-strong)] bg-[var(--accent)]/12` with `reactor-pulse` animation
- **Sub-label:** `text-xs text-slate-400` — mode description beneath the mode name

### Chat Message Bubbles
- **VERONICA (assistant):** `border-[var(--accent)]/20 bg-[var(--accent)]/[0.06] text-[var(--accent-text)]` — contained within the active accent tonal family
- **COMMANDER (user):** `ml-auto max-w-[90%] border-pink-300/20 bg-pink-400/[0.07] text-pink-50` — plasma-alert tint distinguishes human input from AI output without a directional layout shift
- **Streaming cursor:** 2px wide, accent-strong color, `animate-pulse` — the typewriter indicator at the live response edge

### Status Indicators
- **Online dot (semantic):** 6px circle, `bg-emerald-400` with matching glow — fixed green, not part of the accent system
- **Mode dot (branded):** `bg-[var(--accent-strong)]` with `status-blink` animation — for mode-aware live indicators

## 6. Do's and Don'ts

### Do:
- **Do** let the modal accent do the elevation work. If an element is live, interactive, or active, the accent border or ambient bloom signals it. No supplementary ornament required.
- **Do** use uppercase + tracking (`letter-spacing: 0.18em`) for all system-generated labels: mode names, section identifiers, status strings. Human-authored content never gets this treatment.
- **Do** keep glow at the panel perimeter only. Every `.hud-panel` interior is flat.
- **Do** add `break-words min-w-0` to any text element inside a flex container. The system renders variable-length data (email addresses, contact names, AI responses) — overflow must be handled explicitly everywhere.
- **Do** add `shrink-0` to timestamps, dates, and icon buttons in flex rows. These must not compress under text pressure.
- **Do** use `ease-out` (0.2s-0.4s) for all state transitions. The UI responds; it does not perform.

### Don't:
- **Don't** use gradient text (`background-clip: text` with a gradient fill). The system uses solid accent colors only. Weight and size carry emphasis.
- **Don't** add glassmorphism decoratively. The `backdrop-filter: blur(18px)` on `.hud-panel` is structural — it separates the panel from the scanline background. Do not add blur to nested elements, chips, tooltips, or modals for visual effect.
- **Don't** use `border-left` greater than 1px as a colored accent stripe on cards or list items. Internal structure uses full borders, background tints, or nothing.
- **Don't** nest `.hud-panel` inside `.hud-panel`. The corner brackets and ambient glow compound into visual noise. Use tinted background sections (`bg-black/20`, `bg-white/[0.03]`) and hairline borders inside panels.
- **Don't** build gradient hero metrics: big number, small label, gradient accent bar. This is the signature pattern of generic AI SaaS dashboards — the exact register VERONICA must not occupy.
- **Don't** apply the modal accent to static, non-interactive elements at rest. Arc light means "live" or "selected." Using it on decorative borders, section dividers, or illustrations depletes its signal value.
- **Don't** use JetBrains Mono for flavor text, timestamps, or decorative copy. Mono is strictly for machine-generated technical content: IDs, latency values, code, terminal strings.
- **Don't** make it feel like a 2024 AI SaaS product: no purple gradient hero sections, no glassmorphism sidebar, no "your AI assistant is ready" onboarding toast with confetti. VERONICA has no onboarding — it is already operational.
