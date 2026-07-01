# AGENTS.md

This repository's agent guidance is maintained canonically in **[CLAUDE.md](CLAUDE.md)** —
read it first. It covers the architecture, conventions, the three test tiers, deployment,
and a **Lessons learned** section.

Codex / other agents: follow CLAUDE.md. When you discover something that was not
well done or was non-obvious, add it to the **Lessons learned** list in CLAUDE.md so the
mistake isn't repeated. Keep both files pointing at the same single source of truth.

Quick reminders:
- Non-secret config → `config.yaml` (`deps/config.py`); secrets → `.env`. Never commit
  `.env`, `config.yaml`, or the Google service-account JSON.
- All SQL lives in `deps/*_data_access.py`; cogs hold none.
- Run `make test` (unit + integration + system) and `make lint` before finishing.
- Wrap network/SDK calls in `asyncio.to_thread`; lazy-import heavy deps.
