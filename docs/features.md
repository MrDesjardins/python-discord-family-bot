# Features

## 1. Reminders

`/setreminder message [date] [time]`

- **No `date`** → a **daily** reminder. The bot pings the author every day at
  `reminders.default_time` (config, default `08:30`, in `reminders.timezone`) until
  **someone reacts to the posted reminder message with any emoji**, which stops it.
- **`date` given** (`YYYY-MM-DD`, optional `time` `HH:MM`, default `08:30`) → a
  **one-time** reminder that pings the author once at that local date/time.

Reminders are posted into `channels.reminder`. Other commands:

- `/listreminders` — list active reminders (id, who, when, preview).
- `/cancelreminder id` — deactivate a reminder by id.

Implementation: `cogs/reminders.py`, `deps/reminder_data_access.py`, dispatched by the
60-second loop in `cogs/tasks.py`. Recurring reminders dedupe per local day via
`last_reminded_date`; one-time reminders store a UTC `remind_at` and fire once.

## 2. Google Calendar reminders

The bot watches the calendar named `calendar.name` (default **"Équipe PM"**) and posts
a reminder into `channels.calendar` **`calendar.reminder_lead_minutes` (default 30)**
minutes before each event.

- `poll_loop` refreshes events from Google every `calendar.poll_interval_minutes`
  (default 15) up to `calendar.lookahead_hours` (default 48) ahead, storing them in the
  `calendar_event` table.
- `reminder_loop` (60s) posts for events starting within the lead window that have not
  been reminded, then marks them reminded. A rescheduled event (changed start time)
  becomes eligible to remind again.

Requires a Google **service account** whose JSON key path is in
`GOOGLE_SERVICE_ACCOUNT_FILE`, with the calendar **shared** to its email. See
[google-setup.md](google-setup.md). If disabled in config or no credentials are present,
the calendar loops simply don't start (logged, bot keeps running).

## 3. AI Q&A grounded on family chat

Mention the bot (`@FamilyBot what did we decide about the trip?`).

1. Every text-channel message is archived into the `message` table.
2. A background loop embeds messages locally with **sentence-transformers**
   (`ai.embedding_model`, default `all-MiniLM-L6-v2`) — chat content is never sent out
   merely to be vectorized.
3. On a question, the bot embeds it, scores every stored message by
   `ai.similarity_weight × similarity + (1 − weight) × recency` (recency half-life
   `ai.recency_halflife_days`), takes the top `ai.max_context_messages` (default 50), and
   sends only those excerpts to OpenAI (`ai.model`, default `gpt-4o-mini`).

Restrict where the bot answers by setting `channels.ai`; omit it to answer anywhere.

## Not built: Google Photos

A random-photo poster was requested but **dropped**: since 31 Mar 2025 the Google Photos
Library API can only access media the app itself uploaded, so an unattended bot can't
pull from a personal library. A Google Drive folder or a local folder is the viable
path if revisited later — see the lessons note in `AGENTS.md`.
