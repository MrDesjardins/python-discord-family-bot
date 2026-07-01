# Discord bot setup (Developer Portal)

How to create the bot application, enable the right **privileged intents**, grant the
correct **permissions**, and invite it to your family server. Do this once per bot
(repeat for a separate `dev` bot if you want one).

The bot token(s) produced here are **secrets** and go in `.env`
(`BOT_TOKEN`, `BOT_TOKEN_DEV`) — never in `config.yaml` or git. See
[configuration.md](configuration.md).

## 1. Create the application + bot

1. Go to <https://discord.com/developers/applications> → **New Application**, name it
   (e.g. `FamilyBot`). Accept the terms.
2. Open the **Bot** tab. The bot user is created with the application.
3. **Reset Token** → **Copy**. This is your `BOT_TOKEN`. Paste it into `.env`:
   ```
   BOT_TOKEN=your-token-here
   ```
   A token is shown only once — if you lose it, reset again.
4. (Optional) Repeat steps 1–3 with a second application for a dev bot and store its
   token as `BOT_TOKEN_DEV`. `python3 bot.py` uses `BOT_TOKEN_DEV` when `ENV=dev`
   (the default) and `BOT_TOKEN` when `ENV=prod`.

## 2. Enable the privileged gateway intents

Still on the **Bot** tab, scroll to **Privileged Gateway Intents** and enable:

| Intent | Why the bot needs it |
| --- | --- |
| **Message Content Intent** | Read the text of messages so it can archive them for AI grounding and read `@FamilyBot` questions. Without it `message.content` is empty and AI Q&A returns nothing. |
| **Server Members Intent** | Resolve member display names when archiving messages and when pinging reminder authors. |

> **Presence Intent is NOT needed** — leave it off.

These map to the intents the bot requests in code (`deps/mybot.py`): `message_content`,
`members`, `messages`, `reactions`/`guild_reactions`. The reaction intents are part of
the default (non-privileged) set, so only the two above need the toggle. If either
privileged toggle is off, the gateway connection still works but the corresponding
feature silently breaks.

> A bot in **100+ servers** must get these intents verified by Discord. A private family
> bot is well under that, so no verification is required.

## 3. Choose bot permissions

The bot needs, at minimum:

| Permission | Used for |
| --- | --- |
| **View Channels** | See the reminder / calendar / AI channels at all. |
| **Send Messages** | Post reminders, calendar pings, and AI answers. |
| **Read Message History** | Let `message.reply(...)` reference the question message; archive context. |
| **Embed Links** | Render the calendar event link nicely (optional but recommended). |

The bot does **not** add reactions itself (users react to acknowledge reminders), so
*Add Reactions* is not required. It never needs *Manage Messages*, *Mention Everyone*
(mentions are restricted in code via `AllowedMentions`), or any moderation permissions.

## 4. Invite the bot (OAuth2 URL)

1. **OAuth2 → URL Generator**.
2. **Scopes**: check **`bot`** and **`applications.commands`** (the latter is required
   for the `/setreminder`, `/listreminders`, `/cancelreminder`, `/reloadconfig` slash
   commands to register).
3. **Bot Permissions**: tick the four permissions from §3 (View Channels, Send Messages,
   Read Message History, Embed Links). This produces the permissions integer **`84992`**.
4. Copy the generated URL — it looks like:
   ```
   #Prod
   https://discord.com/oauth2/authorize?client_id=1521661969503883295&permissions=580550729624640&integration_type=0&scope=bot
   #Dev
   https://discord.com/oauth2/authorize?client_id=1521673429156364408&permissions=580550729624640&integration_type=0&scope=bot
   ```
5. Open it in a browser, pick your family server, and **Authorize**. You must have
   *Manage Server* on that server to add a bot.

After joining, make sure the bot's role can actually see and post in the specific
reminder / calendar / AI channels — channel-level permission overrides can still block
a bot that has the server-wide permission.

## 5. Get the IDs for `config.yaml`

The bot is told which server and channels to use via `config.yaml` (not slash commands):

1. In Discord: **User Settings → Advanced → Developer Mode** → on.
2. Right-click the **server** → **Copy Server ID** → `guild_id`.
3. Right-click each target **channel** → **Copy Channel ID** → `channels.reminder`,
   `channels.calendar`, and (optionally) `channels.ai`.

```yaml
guild_id: 123456789012345678
channels:
  reminder: 123456789012345678
  calendar: 123456789012345678
  ai: 123456789012345678   # omit/null => bot answers @-mentions in any channel
```

## 6. First run

```bash
uv run bot.py
```

On a healthy start you should see `events: logged in as FamilyBot#1234; synced N
command(s)`. The slash commands are synced **globally** on `on_ready`; a global sync can
take up to ~1 hour to appear the very first time (subsequent syncs are fast). If commands
don't show up, confirm the `applications.commands` scope was included in the invite.

## Troubleshooting

- **Slash commands missing** → the invite lacked `applications.commands`; re-invite with
  the §4 URL (no need to kick the bot first).
- **AI answers are empty / “no context”** → Message Content Intent is off, or the bot
  can't see the channel where people chat.
- **Reminders post but the author isn't pinged by name** → Server Members Intent is off.
- **Bot online but silent in a channel** → channel-level permission override removes
  *View Channels* / *Send Messages*; fix the channel's permissions for the bot role.
- **`BOT_TOKEN(_DEV) not found … Cannot start`** → the token isn't in `.env`, or `ENV`
  selects the other variable than the one you set.
</content>
