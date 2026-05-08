# VERONICA — Improvements & Pending Work

## Pending Tests

### Semantic Memory
- [ ] Save individual notes/memories with `COMMANDER note: ...` and `COMMANDER remember this: ...`
- [ ] Confirm storage: response should say "Sir, note stored:" or "Sir, committed to long-term memory:"
- [ ] Re-saving same content should reply "Sir, that's already in memory" (dedup check)
- [ ] `COMMANDER what do I know about Veronica` should return the Veronica note (keyword fallback)
- [ ] `COMMANDER find notes about coding style` should return the "clean minimal code" note semantically
- [ ] Pull `nomic-embed-text` (`ollama pull nomic-embed-text`) for proper vector search
- [ ] After pulling embed model, verify `/search?q=JARVIS` returns ranked results
- [ ] Delete duplicate Pranav memory via `DELETE /memory/{id}` (stored twice in earlier test)

### Auto-Journal
- [ ] `COMMANDER how was my day` — should generate + return today's journal entry
- [ ] `COMMANDER write my journal` — same trigger
- [ ] Journal tab in UI shows sidebar with last 14 entries
- [ ] "Write Today" button in Journal tab generates on-demand
- [ ] Scheduler auto-generates at 10:30 PM IST daily (verify APScheduler logs)

### WhatsApp Auto-Reply
- [ ] `COMMANDER reply to Pranav Gohil on his reply` — fetches conversation, auto-composes reply, shows confirmation
- [ ] Confirm → sends message
- [ ] `COMMANDER you suggest` — same flow, should compose without being told what to say

---

## Next Up (in order)

1. **Scheduled WhatsApp messages** — "remind me to message Pranav tomorrow at 10am" → queues and sends automatically
2. **News digest UI** — category tabs, auto-refresh, mark-as-read
3. **Notion bidirectional sync** — pull pages from Notion on a schedule (currently push-only)

---

## Known Issues / Tech Debt

- Semantic search threshold (0.3) may need tuning per embedding model — nomic-embed-text vs chat model fallback behave differently
- Notes saved before `nomic-embed-text` was pulled won't have embeddings; backfill runs every 10 min but only if Ollama is online
- `COMMANDER` prefix stripping added — all intent routing now works with COMMANDER prefix
- Multi-command messages (4 items in one send) still only stores the first matching prefix; send commands one at a time
