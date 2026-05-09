# VERONICA — Improvements & Pending Work

## Pending Tests

### Semantic Memory
- [x] Save individual notes/memories with `COMMANDER note: ...` and `COMMANDER remember this: ...`
- [x] Confirm storage: response says "Sir, note stored:" or "Sir, committed to long-term memory:"
- [x] Re-saving same content replies "already in memory" (exact + fuzzy 90% dedup)
- [x] `COMMANDER what do I know about Veronica` — LLM-synthesized answer, not raw note dump
- [ ] `COMMANDER find notes about coding style` — needs `nomic-embed-text` pulled
- [ ] Pull `nomic-embed-text` (`ollama pull nomic-embed-text`) for proper vector search
- [ ] After pulling embed model, verify `/search?q=JARVIS` returns ranked results
- [x] Delete duplicate Pranav memory — removed IDs 3 & 4

### Auto-Journal
- [x] `COMMANDER how was my day` — sharp activity log, not diary prose
- [x] `COMMANDER write my journal` — same trigger
- [x] Journal tab in UI shows sidebar with entries (up to 14)
- [x] "Write Today" button — force-regenerates + shows "✓ Done" feedback
- [x] Scheduler auto-generates at 10:30 PM IST daily (confirmed in APScheduler logs)

### WhatsApp Auto-Reply
- [x] `COMMANDER reply to Pranav/Darsh on his reply` — fetches conversation live, auto-composes reply
- [x] Confirm → sends message
- [ ] `COMMANDER you suggest` — auto-compose with no explicit instruction

---

## Next Up (in order)

1. **`COMMANDER you suggest`** — last untested WhatsApp item
2. **Scheduled WhatsApp messages** — "remind me to message Pranav tomorrow at 10am"
3. **News digest UI** — category tabs, auto-refresh, mark-as-read
4. **Notion bidirectional sync** — pull pages from Notion (currently push-only)

---

## Known Issues / Tech Debt

- Semantic search needs `nomic-embed-text` for proper vector matching — keyword fallback active until then
- Embedding circuit breaker: 60s cooldown when Ollama offline (no WARNING spam)
- WhatsApp startup slow at high RAM — Brave headless is heavy; extra memory flags added
- Multi-command messages only processes the first match — send one command at a time
