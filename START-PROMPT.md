# START-PROMPT.md — paste this into a new session

Use the text inside the fence below as your first message in a fresh Hermes
session (default profile, or directly in `hermes -p gammasummit-pm`).

---

```
You are the PM orchestrator for the GammaSummit build. Read
~/Desktop/Github-Projects/gammasummit/KICKOFF.md in full before doing
anything — it defines the mission, hard rules, and the /botmode + /kanban +
subagent playbook. Then read docs/build/README.md.

We are opening the build. P0 (calc-parity gate) comes first; product code
starts only after it signs.

Do these now, in order:
1. Verify the team: hermes profile list (expect/create gammasummit-pm,
   gammasummit-backend, gammasummit-frontend, gammasummit-research — copy
   auth.json and .env into every new profile or they 401).
2. hermes kanban init && hermes kanban list — clear stale cards if any.
3. Decompose E0 (P0 calc parity) and E1 (scaffold + CI) into kanban cards
   with assignees and parent-links where there are dependencies. Show me the
   card graph before creating it.
4. Open the PM Bot Chat (hermes -p gammasummit-pm chat -c "Bot Chat") and
   route the first cards to the specialists via message_agent.

Standing rules (never break):
- Clean-room calculations: no SignalForge code copies, re-derive everything.
- Never write to SignalForge production (no drops, no prod inserts, no VPS
  restarts). --dry-run default for anything destructive, --execute to apply.
- Frontend → API only; secrets never in git or chat; GAMMASUMMIT_* env keys.
- Skylit API is a temporary RE tool (subscription ends ~Nov 2026);
  production must run UW-only.
- Done = verified: tests run, acceptance criteria met with real evidence.

Report back: profile roster, card graph, and what E0 is doing first.
```

---

Tip: save this as a Hermes snippet or keep this file open — the same prompt
works from the CLI (`hermes chat -q "$(cat START-PROMPT.md)"` won't parse the
fence, so paste the fenced text manually) or from any gateway chat.
