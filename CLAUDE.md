# CLAUDE.md

Guidance for Claude Code / Codex when working in this repository. Keep this file
current: when something turns out to be wrong or non-obvious, add it to **Lessons
learned** so we don't repeat it.

## Project Overview

A private family Discord bot with three features:
- **Reminders**: `/setreminder` posts to a configured channel and pings the author daily
  (until acknowledged with an emoji) or once on a specific date.
- **Google Calendar**: mirrors the "Équipe PM" calendar and reminds 30 min before events.
- **AI Q&A**: `@`-mention answers via OpenAI, grounded on archived family chat retrieved
  with local sentence-transformers embeddings (similarity × recency).

## Commands

```bash
make run             # python3 bot.py  (ENV=dev->BOT_TOKEN_DEV, ENV=prod->BOT_TOKEN)
make test            # unit + integration + system test tiers
make unit-test / integration-test / system-test
make lint            # black --check + pylint + mypy
make format          # black
```

Always run `make test` and `make lint` before declaring work done.

## Architecture (see docs/architecture.md)

- **Entry**: `bot.py` → `deps/bot_singleton.py` → `deps/mybot.py` (auto-loads `cogs/*`).
- **Cogs**: `events.py` (sync, archive, AI mention), `reminders.py`, `calendar_cog.py`,
  `tasks.py` (reminder + embedding loops), `admin.py` (`/reloadconfig`).
- **deps/**: `config.py` (YAML), `database.py` (`database_manager`, SQLite+WAL),
  `*_data_access.py` (all SQL), `google_calendar.py`, `ai/` (embeddings + OpenAI),
  `functions_date.py`, `models.py`, `values.py`, `log.py`.

## Conventions

- **Config vs secrets**: non-secret settings (channels, timezone, AI tuning, calendar)
  live in `config.yaml`, loaded via `deps/config.py` (`get_config()`); it is
  authoritative — there are no slash commands to set channels. Secrets come only from
  `.env` / `os.getenv` (`BOT_TOKEN`, `OPENAI_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_FILE`).
- **No SQL in cogs.** All SQL lives in `deps/*_data_access.py` against `database_manager`.
- **Logging** via `deps/log.py` (`print_log`/`print_warning_log`/`print_error_log`). No
  bare `print`.
- **Don't block the event loop**: wrap OpenAI / Google / sentence-transformers calls in
  `asyncio.to_thread`.
- **Lazy-import heavy/optional deps** (`sentence_transformers`, `googleapiclient`,
  `google.oauth2`) inside the function that needs them, so imports/tests stay light and a
  missing optional dep degrades gracefully.
- **Keep core logic pure**: ranking (`embeddings.rank_messages`) and scheduling helpers
  take weights / `now` as parameters so unit tests need no config, DB, or model.
- Datetimes stored as ISO strings; scheduling is tz-aware (pytz) via `functions_date.py`.
  One-time reminders store UTC; recurring store `HH:MM` + `last_reminded_date` (local).
- Command-name constants in `deps/values.py`; tunables in `config.yaml`.

## Testing (see docs/testing.md)

Three tiers by filename: `*_unit_test.py` (pure/mocked, no DB), `*_integration_test.py`
(modules together, `db` fixture), `*_system_test.py` (real SQL CRUD on a copied seeded DB
via the `system_db` fixture). Mirror the source module name. Every feature needs at least
unit + integration coverage; data-access changes need a system test.

## Deployment (see docs/deployment.md)

`./deploy.sh` from the desktop → git push → SSH to the mini-pc (10.0.0.181, user
`pdesjardins`) → `deployment/update.sh` (git pull, `uv sync`, refresh systemd, restart).
The `systemd/familybot.service` unit sets `WorkingDirectory` so `.env` and `config.yaml`
are read from the project folder; passwordless via SSH keys + scoped NOPASSWD sudoers.

## Lessons learned (refine this list whenever something bites us)

- **Google Photos is a dead end for automation.** Since 2025-03-31 the Photos Library API
  only accesses media the app itself uploaded; an unattended bot can't read a personal
  library. Use a Google Drive folder or a local folder instead. (This is why the photo
  feature was dropped.)
- **`cursor.lastrowid` is `int | None`** — wrap as `int(cur.lastrowid or 0)` to satisfy
  mypy and avoid a None surprise.
- **`Cog.cog_unload` must be `async def`** in discord.py (the base method is a coroutine);
  a sync override fails mypy and may not be awaited.
- **System-test seed data must use stable dates** (e.g. far-future) so real-time-based
  cleanup like `delete_past_events(now - 1d)` doesn't delete seed rows and flake tests.
- **mypy needs stubs** for `PyYAML` (`types-PyYAML`); third-party SDKs without stubs go in
  the `ignore_missing_imports` override in `pyproject.toml`.
- **Calendar service accounts only see shared calendars.** If `find_calendar_id_by_name`
  returns None, the calendar wasn't shared with the service-account email.
- **A calendar *shared* with a service account never appears in `calendarList()`.** The
  ACL share grants access but doesn't subscribe the account (no inbox to accept the
  invite), so name lookup can't find it. Set `calendar.calendar_id` in `config.yaml` and
  read via `events().list(calendarId=…)` directly. `tools/list_calendars.py <id>` tests
  this path.
- **Slash-command permission checks must use `app_commands.checks.*`**, not
  `commands.has_permissions`. The latter attaches to `__commands_checks__`, which the
  app-command tree ignores, so the check silently becomes a no-op (anyone can run the
  command). Put `@app_commands.checks.has_permissions(...)` *below* `@app_commands.command`.
```
