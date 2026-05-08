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

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_PATH, clientId: "veronica" }),
  puppeteer: { headless: true, args: ["--no-sandbox", "--disable-setuid-sandbox"] },
});

function pushMessage(entry) {
  // Deduplicate by id
  if (messages.some(m => m.id === entry.id)) return;
  messages.unshift(entry);
  if (messages.length > MAX_MESSAGES) messages.splice(MAX_MESSAGES);
}

client.on("qr", async (qr) => {
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

client.on("ready", async () => {
  isReady = true;
  isInitializing = false;
  currentQR = null;
  console.log("[VERONICA] WhatsApp connected ✓");

  // Load recent message history from the top 20 recent chats
  try {
    const chats = await client.getChats();
    const recent = chats.slice(0, 20);
    for (const chat of recent) {
      const msgs = await chat.fetchMessages({ limit: 8 });
      for (const msg of msgs) {
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
    console.log(`[VERONICA] Loaded ${messages.length} messages from history`);
  } catch (err) {
    console.error("[VERONICA] Failed to load message history:", err);
  }
});

client.on("auth_failure", (msg) => {
  isReady = false;
  isInitializing = false;
  currentQR = null;
  console.error("[VERONICA] WhatsApp auth failed:", msg, "— session may be stale, restart to get a new QR");
});

client.on("disconnected", (reason) => {
  isReady = false;
  isInitializing = false;
  console.log("[VERONICA] WhatsApp disconnected:", reason);
});

// Incoming messages
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

// Sent messages (fromMe)
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

client.initialize().catch((err) => {
  console.error("[VERONICA] WhatsApp init error:", err);
});

app.get("/status", (req, res) => {
  res.json({ ready: isReady, has_qr: currentQR !== null, initializing: isInitializing });
});

app.get("/qr", (req, res) => {
  res.json({ ready: isReady, qr: currentQR });
});

app.get("/messages", (req, res) => {
  const limit = Math.min(parseInt(req.query.limit || "50", 10), MAX_MESSAGES);
  res.json({ messages: messages.slice(0, limit), total: messages.length });
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
      // Already a chat ID
      chatId = to;
    } else if (/^\+?[\d\s\-]+$/.test(to.trim())) {
      // Phone number — strip formatting
      const digits = to.replace(/[\s\-\(\)]/g, "").replace(/^\+/, "");
      chatId = `${digits}@c.us`;
    } else {
      // Name lookup via WhatsApp contacts
      const contacts = await client.getContacts();
      const lower = to.toLowerCase().trim();
      const match = contacts.find((c) => {
        const name = (c.name || c.pushname || "").toLowerCase();
        return name === lower || name.startsWith(lower) || lower.startsWith(name.split(" ")[0]);
      });
      if (!match) {
        return res.status(404).json({
          ok: false,
          error: `Contact "${to}" not found in WhatsApp. Use their phone number instead.`,
        });
      }
      chatId = match.id._serialized;
      resolvedName = match.name || match.pushname || to;
    }

    const result = await client.sendMessage(chatId, text);
    res.json({ ok: true, id: result.id.id, contact: resolvedName });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.post("/reset", async (req, res) => {
  console.log("[VERONICA] Session reset requested — clearing session and restarting");
  isReady = false;
  isInitializing = true;
  currentQR = null;
  try {
    await client.destroy();
  } catch (_) { /* ignore */ }
  // Delete session data so a fresh QR is generated
  const fs = require("fs");
  const sessionDir = path.join(SESSION_PATH, "session-veronica");
  if (fs.existsSync(sessionDir)) {
    fs.rmSync(sessionDir, { recursive: true, force: true });
    console.log("[VERONICA] Session cleared");
  }
  // Reinitialize
  setTimeout(() => client.initialize().catch(console.error), 500);
  res.json({ ok: true, message: "Session reset initiated — new QR will appear shortly" });
});

app.listen(PORT, () => {
  console.log(`[VERONICA] WhatsApp service on port ${PORT}`);
});
