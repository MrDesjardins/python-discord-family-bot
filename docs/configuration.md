# Configuration

Two layers: **non-secret** YAML and **secret** environment variables.

## `config.yaml` (non-secret)

Copy `config.example.yaml` → `config.yaml` (gitignored) and fill in IDs. Loaded by
`deps/config.py`; authoritative for channels, timezone, AI tuning, and calendar.

| Key | Meaning | Default |
| --- | --- | --- |
| `guild_id` | Your Discord server ID | — (required) |
| `channels.reminder` | Channel where `/setreminder` posts/pings | — (required) |
| `channels.calendar` | Channel for calendar event reminders | — (required) |
| `channels.ai` | Restrict `@`-mention answers to this channel | null (answer anywhere) |
| `ai.model` | OpenAI chat model | `gpt-4o-mini` |
| `ai.embedding_model` | sentence-transformers model | `all-MiniLM-L6-v2` |
| `ai.max_context_messages` | Top-k messages retrieved as context | `50` |
| `ai.recency_halflife_days` | Recency weighting half-life | `14` |
| `ai.similarity_weight` | Blend of similarity vs. recency (0..1) | `0.7` |
| `reminders.default_time` | Default reminder time `HH:MM` | `08:30` |
| `reminders.timezone` | IANA timezone for scheduling | `America/Los_Angeles` |
| `calendar.enabled` | Turn the calendar feature on/off | `false` |
| `calendar.name` | Calendar to watch (matched by name) | `Équipe PM` |
| `calendar.reminder_lead_minutes` | Minutes before an event to ping | `30` |
| `calendar.poll_interval_minutes` | How often to refresh from Google | `15` |
| `calendar.lookahead_hours` | How far ahead to sync | `48` |

Apply changes without restarting with **`/reloadconfig`** (admin only).

### Getting IDs

Enable **Developer Mode** in Discord (Settings → Advanced). Right-click the server icon
→ *Copy Server ID*; right-click a channel → *Copy Channel ID*.

## `.env` (secret)

Copy `.env.example` → `.env` (gitignored). It is read from the bot's working directory
at startup (python-dotenv), including under systemd.

| Variable | Meaning |
| --- | --- |
| `ENV` | `dev` (uses `BOT_TOKEN_DEV`), `prod` (uses `BOT_TOKEN`), or `test` |
| `BOT_TOKEN` / `BOT_TOKEN_DEV` | Discord bot tokens |
| `OPENAI_API_KEY` | OpenAI key for AI Q&A |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path to the Google service-account JSON (calendar) |
| `CONFIG_FILE` | Optional override of the YAML path (default `config.yaml`) |
| `DATABASE_NAME` | Optional override of the SQLite file (default `family_bot.db`) |

Never put secrets in `config.yaml`, and never commit `.env`, `config.yaml`, or the
service-account JSON (all gitignored).
