# Architecture

## High-level

```
bot.py
  └─ BotSingleton ── MyBot (discord.py Bot)
        └─ setup_hook() auto-loads every cogs/*.py
              ├─ cogs/events.py        on_ready (command sync), on_message (archive + AI mention)
              ├─ cogs/reminders.py     /setreminder, /listreminders, /cancelreminder, emoji ack
              ├─ cogs/calendar_cog.py  poll Google Calendar + 30-min event reminders
              ├─ cogs/tasks.py         reminder dispatch + daily-summary + embedding backfill loops
              └─ cogs/admin.py         /reloadconfig

deps/                         business logic + data access (no Discord types leak in)
  config.py                   YAML config loader (authoritative for channels/timezone/AI/calendar)
  database.py                 DatabaseManager (SQLite + WAL) + schema, single `database_manager`
  models.py                   Reminder, CalendarEvent dataclasses (from_db_row)
  reminder_data_access.py     reminder table CRUD
  message_data_access.py      message table (archive + embeddings)
  calendar_data_access.py     calendar_event table CRUD
  google_calendar.py          service-account auth, find calendar by name, fetch events
  functions_date.py           timezone-aware scheduling helpers (pytz)
  channel_visibility.py       channels/threads a member can read (AI permission filter)
  ai/embeddings.py            sentence-transformers + recency-weighted ranking
  ai/ai_functions.py          OpenAI chat grounded on retrieved context
  values.py                   command-name constants + small fallbacks
  log.py                      print_log / print_warning_log / print_error_log
```

## Layering rules

- **Cogs** translate Discord events/commands into calls on `deps/`. They hold no SQL.
- **`deps/*_data_access.py`** own all SQL and talk to `database_manager`.
- **`deps/config.py`** is the single source of truth for non-secret settings. Secrets
  come only from environment variables (`.env`).
- Network/SDK calls (OpenAI, Google, sentence-transformers) are **run off the event
  loop** via `asyncio.to_thread` so the bot stays responsive.

## Configuration vs. secrets

| Kind | Where | Examples |
| --- | --- | --- |
| Non-secret | `config.yaml` (gitignored copy of `config.example.yaml`) | channel IDs, timezone, AI top-k, calendar name |
| Secret | `.env` (read from the working directory) | `BOT_TOKEN`, `OPENAI_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_FILE` |

`config.yaml` is authoritative: there are no slash commands to set channels. Edit the
file and run `/reloadconfig` (or restart) to apply.

## Database schema (`deps/database.py`)

- `reminder` — user reminders (recurring-daily or one-time).
- `message` — archived guild messages + their embedding blob (float32 bytes).
  `parent_channel_id` is set for public-thread messages so visibility can match the
  parent channel even after the thread auto-archives; NULL for regular channels and
  private threads.
- `calendar_event` — mirror of upcoming Google Calendar events + `reminded` flag.

SQLite runs in WAL mode. The single `database_manager` instance owns the connection;
tests swap the database file via `set_database_name()`.

## Data flow

**Reminder (recurring)**: `/setreminder` (empty `when`) → `functions_when.parse_when` →
`reminder_data_access.create_recurring_reminder` → posts a message, stores its id →
`tasks.reminder_loop` (60s) pings daily at the configured time → emoji reaction →
`reminders.on_raw_reaction_add` → `acknowledge_reminder`. A one-time `when`
("tomorrow", "fri 6pm", ISO date) instead routes to `create_onetime_reminder`; the
`when` field is typed with `functions_when.suggest_when` autocomplete.

**Calendar**: `calendar_cog.poll_loop` (configurable interval) → `google_calendar.fetch_upcoming_events`
→ `calendar_data_access.upsert_event` → `reminder_loop` (60s) → `get_events_needing_reminder`
(start within lead window, not reminded) → post + `mark_event_reminded`.

**Daily summary**: `tasks.daily_summary_loop` (60s) → `daily_summary.is_summary_due` (once per
day at the configured time) → `get_events_in_range` (today) + `reminders_for_day` →
`daily_summary.format_summary` → post to the calendar channel (archived for the AI). The last
posted date is persisted via `bot_state_data_access` so a restart doesn't re-post it.

**AI**: every guild message → `events.on_message` → `message_data_access.store_message`
→ `tasks.embedding_loop` (30s) embeds new rows → `@mention` → `channel_visibility.visible_channel_ids`
(channels the asker can read, from live Discord role/overwrite permissions; private
threads additionally require thread membership or `manage_threads`) →
`ai_functions.answer_question` → retrieval restricted to those channels (a message also
matches via its stored `parent_channel_id`, keeping public-thread history visible after
the thread auto-archives) → embed question, `embeddings.rank_messages`
(similarity × recency), top-k → OpenAI. A member who can see no channels gets no
archived context (fail-closed).
