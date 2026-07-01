# Family Discord Bot

A private Discord bot for a family server:

1. **Reminders** — `/setreminder` posts to a channel and pings you daily-until-acknowledged
   or once on a specific date.
2. **Google Calendar** — watches the **"Équipe PM"** calendar and reminds the family
   **30 minutes before** each event.
3. **AI Q&A** — mention the bot to ask a question; it answers with OpenAI, grounded on
   your family's chat history via local, open-source vector search.

Non-secret settings live in `config.yaml`; secrets live in `.env`. Full docs in
[`docs/`](docs/): [architecture](docs/architecture.md) · [features](docs/features.md) ·
[Discord setup](docs/discord-setup.md) · [configuration](docs/configuration.md) ·
[Google setup](docs/google-setup.md) · [deployment](docs/deployment.md) ·
[testing](docs/testing.md).

---

## Getting started

### 1. Create the Discord bot (Developer Portal)

Quick version (full walkthrough with intents, permissions, and troubleshooting in
[docs/discord-setup.md](docs/discord-setup.md)):

1. <https://discord.com/developers/applications> → **New Application** → **Bot** tab →
   **Reset Token** → copy it into `.env` as `BOT_TOKEN` (and `BOT_TOKEN_DEV` for a
   separate dev bot).
2. **Bot → Privileged Gateway Intents** → enable **Message Content Intent** and
   **Server Members Intent** (Presence is not needed).
3. **OAuth2 → URL Generator** → scopes `bot` + `applications.commands`; permissions
   *View Channels*, *Send Messages*, *Read Message History*, *Embed Links*. Open the URL
   to invite the bot.
4. Enable **Developer Mode** (Settings → Advanced) to copy the server ID and channel IDs
   into `config.yaml`.

### 2. Install locally (Python 3.10–3.12)

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"        # or: pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env              # BOT_TOKEN(_DEV), OPENAI_API_KEY, GOOGLE_SERVICE_ACCOUNT_FILE
cp config.example.yaml config.yaml  # guild_id + channel IDs + settings
```

- Secrets → `.env` (see [configuration.md](docs/configuration.md)).
- Channels / timezone / AI / calendar → `config.yaml`.
- For calendar, set up a Google service account and share the calendar with it —
  see [google-setup.md](docs/google-setup.md).

### 4. Run

```bash
python3 bot.py        # ENV=dev uses BOT_TOKEN_DEV; ENV=prod uses BOT_TOKEN
```

The first AI/embedding use downloads the sentence-transformers model (~90 MB) once.

---

## Commands

| Command | Who | What |
| --- | --- | --- |
| `/setreminder message [date] [time]` | anyone | Daily reminder (no date) or one-time (with date). |
| `/listreminders` | anyone | List active reminders. |
| `/cancelreminder id` | anyone | Cancel a reminder. |
| `/reloadconfig` | admin | Re-read `config.yaml` without restarting. |
| `@FamilyBot <question>` | anyone | AI answer grounded on family chat history. |

Reminder behaviour and AI ranking details are in [features.md](docs/features.md).

---

## Deploy to the mini-pc

From your desktop:

```bash
./deploy.sh           # git push, then SSH to the mini-pc: pull + uv sync + restart service
```

One-time mini-pc setup, passwordless SSH/sudo, and the systemd unit are documented in
[deployment.md](docs/deployment.md).

---

## Development

```bash
make test     # unit + integration + system tiers (see docs/testing.md)
make lint     # black --check + pylint + mypy
make format   # black
```

---

## Project layout

```
bot.py                 entry point
config.example.yaml    template for config.yaml (non-secret settings)
.env.example           template for .env (secrets)
cogs/                  Discord commands + event/loop handlers
deps/                  business logic + data access (config, db, calendar, ai)
deps/ai/               embeddings + OpenAI Q&A
deployment/            update.sh (runs on the mini-pc)
systemd/               familybot.service unit
tests/                 *_unit_test.py / *_integration_test.py / *_system_test.py
docs/                  architecture, features, configuration, google-setup, deployment, testing
```
