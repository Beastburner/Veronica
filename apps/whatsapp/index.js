const express = require("express");
const path = require("path");
const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode");
const qrcodeTerminal = require("qrcode-terminal");

const PORT = parseInt(process.env.PORT || "3001", 10);

const SESSION_PATH = process.env.WA_SESSION_PATH
  || path.join(require("os").homedir(), ".veronica-wa-session");

const app = express();
app.use(express.json());

let isReady = false;
let isInitializing = true;
let currentQR = null;
const messages = [];
const MAX_MESSAGES = 200;

// ── Contact cache (avoid calling getContacts() on every request) ──────────
let _contactsCache = null;
let _contactsCacheAt = 0;
const CONTACTS_TTL_MS = 5 * 60 * 1000; // 5 minutes

async function getCachedContacts() {
  if (_contactsCache && (Date.now() - _contactsCacheAt) < CONTACTS_TTL_MS) {
    return _contactsCache;
  }
  _contactsCache = await client.getContacts();
  _contactsCacheAt = Date.now();
  return _contactsCache;
}

function invalidateContactsCache() {
  _contactsCache = null;
  _contactsCacheAt = 0;
}

// ── Group chat cache ──────────────────────────────────────────────────────
let _groupsCache = null;
let _groupsCacheAt = 0;

async function getCachedGroups() {
  if (_groupsCache && (Date.now() - _groupsCacheAt) < CONTACTS_TTL_MS) {
    return _groupsCache;
  }
  const chats = await client.getChats();
  _groupsCache = chats.filter(c => c.isGroup);
  _groupsCacheAt = Date.now();
  return _groupsCache;
}

function invalidateGroupsCache() {
  _groupsCache = null;
  _groupsCacheAt = 0;
}

// ── Auto-detect system Chrome/Brave/Edge ─────────────────────────────────
const fs = require("fs");
const os = require("os");
function findSystemChrome() {
  if (process.env.CHROME_PATH && fs.existsSync(process.env.CHROME_PATH)) {
    console.log(`[VERONICA] Using CHROME_PATH: ${process.env.CHROME_PATH}`);
    return process.env.CHROME_PATH;
  }
  const home = os.homedir();
  const candidates = [
    // Brave — user-local install (most common on Windows)
    `${home}\\AppData\\Local\\BraveSoftware\\Brave-Browser\\Application\\brave.exe`,
    // Brave — system install
    "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
    "C:\\Program Files (x86)\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
    // Chrome — 64-bit
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    // Chrome — 32-bit
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    // Chrome — user-local install
    `${home}\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe`,
    // Edge (ships with Windows 10/11)
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) {
      console.log(`[VERONICA] Using system browser: ${p}`);
      return p;
    }
  }
  console.log("[VERONICA] No system browser found — using Puppeteer's bundled Chromium");
  return undefined;
}

const CHROME_PATH = findSystemChrome();

// ── Puppeteer flags for low-RAM systems ──────────────────────────────────
const PUPPETEER_ARGS = [
  "--no-sandbox",
  "--disable-setuid-sandbox",
  "--disable-dev-shm-usage",
  "--disable-accelerated-2d-canvas",
  "--no-first-run",
  // Note: --no-zygote removed — conflicts with some Chromium/Brave builds
  "--disable-gpu",
  "--disable-extensions",
  "--disable-background-networking",
  "--disable-sync",
  "--disable-translate",
  "--disable-features=site-per-process,VizDisplayCompositor",
  "--metrics-recording-only",
  "--safebrowsing-disable-auto-update",
  "--disable-default-apps",
  "--mute-audio",
  "--hide-scrollbars",
  "--password-store=basic",
  "--use-mock-keychain",
  // Memory-saving flags for RAM-constrained systems
  "--js-flags=--max-old-space-size=256",
  "--disk-cache-size=1",
  "--media-cache-size=1",
  "--renderer-process-limit=2",
  "--disable-dev-tools",
];

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_PATH, clientId: "veronica" }),
  puppeteer: {
    headless: true,
    executablePath: CHROME_PATH,
    args: PUPPETEER_ARGS,
    timeout: 120_000, // 2-minute browser launch timeout (default is 30s, too low for low-RAM)
  },
});

function pushMessage(entry) {
  if (messages.some(m => m.id === entry.id)) return;
  messages.unshift(entry);
  if (messages.length > MAX_MESSAGES) messages.splice(MAX_MESSAGES);
}

client.on("qr", async (qr) => {
  clearTimeout(_startupWatchdog);
  isInitializing = false;
  console.log("\n[VERONICA] Scan this QR code with WhatsApp:\n");
  qrcodeTerminal.generate(qr, { small: true });
  console.log("\n[VERONICA] Or open http://localhost:3000 → WhatsApp tab\n");
  try {
    currentQR = await qrcode.toDataURL(qr);
  } catch (err) {
    console.error("QR generation error:", err);
    currentQR = null;
  }
});

client.on("ready", () => {
  clearTimeout(_startupWatchdog);
  isReady = true;
  isInitializing = false;
  currentQR = null;
  console.log("[VERONICA] WhatsApp connected ✓");

  // Load history in the background — doesn't block /status or /send
  setImmediate(() => _loadHistoryBackground());
});

async function _loadHistoryBackground() {
  try {
    const chats = await client.getChats();
    // Only top 5 chats, 5 messages each — fast and enough for context
    const recent = chats.slice(0, 5);
    const results = await Promise.all(
      recent.map(chat => chat.fetchMessages({ limit: 5 }).catch(() => []))
    );
    for (let i = 0; i < recent.length; i++) {
      const chat = recent[i];
      for (const msg of results[i]) {
        if (!msg.body) continue;
        pushMessage({
          id: msg.id.id,
          from: msg.fromMe ? "me" : (msg.from || "unknown"),
          fromName: msg.fromMe ? "Me" : (msg._data?.notifyName || chat.name || msg.from || "Unknown"),
          to: msg.fromMe ? (msg.to || chat.id._serialized) : null,
          toName: msg.fromMe ? (chat.name || msg.to) : null,
          body: msg.body,
          timestamp: msg.timestamp,
          isGroup: chat.isGroup,
          fromMe: msg.fromMe,
        });
      }
    }
    messages.sort((a, b) => b.timestamp - a.timestamp);
    console.log(`[VERONICA] History loaded: ${messages.length} messages`);
  } catch (err) {
    console.error("[VERONICA] History load failed (non-fatal):", err.message);
  }
}

client.on("auth_failure", (msg) => {
  isReady = false;
  isInitializing = false;
  currentQR = null;
  console.error("[VERONICA] Auth failed:", msg);
});

client.on("disconnected", (reason) => {
  isReady = false;
  isInitializing = false;
  invalidateContactsCache();
  console.log("[VERONICA] Disconnected:", reason);
});

client.on("message", (msg) => {
  pushMessage({
    id: msg.id.id,
    from: msg.from,
    fromName: msg._data?.notifyName || msg.from,
    to: null,
    toName: null,
    body: msg.body,
    timestamp: msg.timestamp,
    isGroup: msg.from.endsWith("@g.us"),
    fromMe: false,
  });
});

client.on("message_create", (msg) => {
  if (!msg.fromMe) return;
  pushMessage({
    id: msg.id.id,
    from: "me",
    fromName: "Me",
    to: msg.to,
    toName: msg._data?.notifyName || msg.to,
    body: msg.body,
    timestamp: msg.timestamp,
    isGroup: (msg.to || "").endsWith("@g.us"),
    fromMe: true,
  });
});

// ── Startup watchdog — warn if browser hasn't shown QR or ready in 90s ──
const _startupWatchdog = setTimeout(() => {
  if (!isReady && !currentQR) {
    console.warn("[VERONICA] ⚠️  90s elapsed — browser may be stuck (likely low RAM)");
    console.warn("[VERONICA] Tips: close other apps to free RAM, or call POST /reset to restart");
  }
}, 90_000);

client.initialize().catch((err) => {
  clearTimeout(_startupWatchdog);
  console.error("[VERONICA] WhatsApp init error:", err);
});

// ── Routes ────────────────────────────────────────────────────────────────

app.get("/status", (req, res) => {
  res.json({
    ready: isReady,
    has_qr: currentQR !== null,
    initializing: isInitializing,
    browser: CHROME_PATH || "puppeteer-bundled",
  });
});

app.get("/qr", (req, res) => {
  res.json({ ready: isReady, qr: currentQR });
});

app.get("/messages", (req, res) => {
  const limit = Math.min(parseInt(req.query.limit || "50", 10), MAX_MESSAGES);
  res.json({ messages: messages.slice(0, limit), total: messages.length });
});

app.get("/contacts", async (req, res) => {
  if (!isReady) {
    return res.status(503).json({ ok: false, error: "WhatsApp not ready" });
  }
  const raw = (req.query.q || "").trim();
  // Split query into words for word-level matching
  const words = raw.toLowerCase().split(/\s+/).filter(Boolean);
  try {
    const all = await getCachedContacts();
    const contacts = all
      .filter((c) => {
        const id = (c.id && c.id._serialized) || "";
        if (id === "status@broadcast") return false;
        const name = (c.name || c.pushname || "").trim();
        if (!name) return false;
        if (!words.length) return true;
        const nameLower = name.toLowerCase();
        const num = (c.number || "");
        // Match if ALL query words appear somewhere in the name, OR number contains query
        return words.every(w => nameLower.includes(w)) || num.includes(raw);
      })
      .map((c) => {
        const serialized = (c.id && c.id._serialized) || "";
        // id._serialized is "{fullnumber}@c.us" — most reliable source of the full number
        const numberFromId = serialized.endsWith("@c.us")
          ? serialized.replace("@c.us", "")
          : "";
        const number = numberFromId || (c.number || "");
        return {
          name: c.name || c.pushname || "",
          number,
          id: serialized,
          isMyContact: c.isMyContact || false,
        };
      })
      .slice(0, raw ? 20 : 200);
    res.json({ ok: true, contacts, total: contacts.length });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.post("/send", async (req, res) => {
  const { to, text } = req.body || {};
  if (!to || !text) {
    return res.status(400).json({ ok: false, error: "to and text required" });
  }
  if (!isReady) {
    return res.status(503).json({ ok: false, error: "WhatsApp not ready" });
  }
  try {
    let chatId;
    let resolvedName = to;

    if (to.includes("@")) {
      chatId = to;
    } else if (/^\+?[\d\s\-]+$/.test(to.trim())) {
      const digits = to.replace(/[\s\-\(\)]/g, "").replace(/^\+/, "");
      chatId = `${digits}@c.us`;
    } else {
      const lower = to.toLowerCase().trim();
      // 1. Try contacts first
      const contacts = await getCachedContacts();
      const match = contacts.find((c) => {
        const name = (c.name || c.pushname || "").toLowerCase();
        return name === lower || name.startsWith(lower) || lower.startsWith(name.split(" ")[0]);
      });
      if (match) {
        chatId = match.id._serialized;
        resolvedName = match.name || match.pushname || to;
      } else {
        // 2. Fall back to group chats — word-level match
        const words = lower.split(/\s+/).filter(Boolean);
        const groups = await getCachedGroups();
        const groupMatch = groups.find((g) => {
          const gname = (g.name || "").toLowerCase();
          return gname === lower || words.every(w => gname.includes(w)) || words.some(w => gname.includes(w));
        });
        if (!groupMatch) {
          return res.status(404).json({
            ok: false,
            error: `"${to}" not found in contacts or groups. Check the name and try again.`,
          });
        }
        chatId = groupMatch.id._serialized;
        resolvedName = groupMatch.name;
      }
    }

    const result = await client.sendMessage(chatId, text);
    res.json({ ok: true, id: result.id.id, contact: resolvedName });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.get("/conversation", (req, res) => {
  const q = (req.query.q || "").toLowerCase().trim();
  if (!q) return res.json({ messages: messages.slice(0, 20) });
  const words = q.split(/\s+/).filter(Boolean);
  const matches = (m) => {
    const fields = [m.from, m.fromName, m.to, m.toName].map(f => (f || "").toLowerCase());
    const all = fields.join(" ");
    // Full phrase match first
    if (all.includes(q)) return true;
    // Fall back: any single word from the query matches a name field
    return words.some(w => fields[1].includes(w) || fields[3].includes(w));
  };
  const filtered = messages.filter(matches);
  res.json({ messages: filtered.slice(0, 30), contact: q });
});

app.get("/groups", async (req, res) => {
  if (!isReady) return res.status(503).json({ ok: false, error: "WhatsApp not ready" });
  const raw = (req.query.q || "").trim().toLowerCase();
  try {
    const groups = await getCachedGroups();
    const filtered = groups
      .filter(g => !raw || g.name.toLowerCase().includes(raw))
      .map(g => ({
        name: g.name,
        id: g.id._serialized,
        isGroup: true,
        participants: g.participants ? g.participants.length : 0,
      }))
      .slice(0, raw ? 20 : 100);
    res.json({ ok: true, groups: filtered, total: filtered.length });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.post("/contacts/refresh", (req, res) => {
  invalidateContactsCache();
  invalidateGroupsCache();
  res.json({ ok: true, message: "Contacts + groups cache cleared — next request fetches fresh." });
});

app.post("/reset", async (req, res) => {
  console.log("[VERONICA] Session reset requested");
  isReady = false;
  isInitializing = true;
  currentQR = null;
  invalidateContactsCache();
  try {
    await client.destroy();
  } catch (_) { /* ignore */ }
  const fs = require("fs");
  const sessionDir = path.join(SESSION_PATH, "session-veronica");
  if (fs.existsSync(sessionDir)) {
    fs.rmSync(sessionDir, { recursive: true, force: true });
    console.log("[VERONICA] Session cleared");
  }
  setTimeout(() => client.initialize().catch(console.error), 500);
  res.json({ ok: true, message: "Session reset initiated — new QR will appear shortly" });
});

app.listen(PORT, () => {
  console.log(`[VERONICA] WhatsApp service on port ${PORT}`);
});
