# Google Calendar setup (service account)

The bot reads the **"Équipe PM"** calendar using a Google **service account** — a
robot account with its own email. No browser login or token refresh is needed, which is
ideal for a headless mini-pc.

## 1. Create a Google Cloud project + enable the API

1. Go to <https://console.cloud.google.com/> and create (or pick) a project.
2. **APIs & Services → Library → Google Calendar API → Enable**.

## 2. Create the service account + key

1. **APIs & Services → Credentials → Create Credentials → Service account**.
2. Give it a name (e.g. `family-bot`), create it (no roles needed).
3. Open the service account → **Keys → Add key → Create new key → JSON**. A JSON file
   downloads. **This file is a secret.**
4. Note the service account's **email** (looks like
   `family-bot@your-project.iam.gserviceaccount.com`).

## 3. Put the key on the bot machine

Place the JSON next to the bot (or anywhere readable) and point `.env` at it:

```
GOOGLE_SERVICE_ACCOUNT_FILE=/home/pdesjardins/code/python-discord-family-bot/service_account.json
```

The filename patterns `service_account*.json`, `*service-account*.json`, and
`google_credentials*.json` are gitignored.

## 4. Share the calendar with the service account

A service account can only see calendars explicitly shared with it.

1. In Google Calendar (web), find **"Équipe PM"** under *My calendars* / *Other calendars*.
2. **Settings and sharing → Share with specific people → Add people**.
3. Paste the service account **email**, set permission to **"See all event details"**,
   and save.

If the calendar belongs to someone else, they perform this share.

## 5. Enable in config

```yaml
calendar:
  enabled: true
  name: "Équipe PM"
```

Run the bot. On startup you should see a log line like
`calendar: resolved 'Équipe PM' -> <calendarId>`. If instead you see *"no calendar
named … visible to the service account"*, use the diagnostic below.

## 6. Debug "no calendar visible to the service account"

Run the diagnostic — it uses the **same** credentials and read-only scope as the bot, so
it prints exactly what the bot can see:

```bash
make list-calendars      # or: python3 tools/list_calendars.py
```

Interpret the output:

- **"ZERO calendars"** → this is the **expected** result for a calendar that was merely
  *shared* with a service account. Sharing grants access (an ACL entry) but does **not**
  add the calendar to the service account's *calendar list*, and a service account has no
  inbox to "accept" a calendar invite — so `calendarList()` stays empty and name lookup
  can never find it. **Address the calendar by its ID instead** (see below). It does *not*
  mean the share failed.
- **Calendars listed, but `calendar.name` "Does NOT match"** → the calendar is in the list;
  the configured name is just slightly off. The tool prints each name's Unicode code points,
  so an accent mismatch (e.g. `Équipe` stored as NFD `E`+combining-acute vs NFC `É`) is
  visible. `find_calendar_id_by_name` normalizes accents and case, but if the wording
  differs, copy the exact printed name into `calendar.name` in `config.yaml`.

### Use the Calendar ID (the reliable fix for service-account shares)

1. Google Calendar (web) → hover the calendar → **⋮ → Settings and sharing**.
2. Scroll to **Integrate calendar** → copy the **Calendar ID**
   (a secondary calendar looks like `abcd1234@group.calendar.google.com`).
3. Verify the service account can read it directly:
   ```bash
   python3 tools/list_calendars.py <calendar-id>
   ```
   You want `✅ Access works`. If you get `❌ Cannot read this calendar id`, the share
   didn't reach this service account — re-share with the exact `client_email` from the
   JSON key file (`GOOGLE_SERVICE_ACCOUNT_FILE`).
4. Put it in `config.yaml` so the bot skips the (empty) name lookup entirely:
   ```yaml
   calendar:
     enabled: true
     calendar_id: abcd1234@group.calendar.google.com
   ```

To confirm which service-account email you actually shared with, look at `client_email`
inside the JSON key file that `GOOGLE_SERVICE_ACCOUNT_FILE` points to — that is the exact
address the calendar must be shared with.

## Notes & limits

- Scope used: `https://www.googleapis.com/auth/calendar.readonly` (read only).
- The bot only ever reads; it never writes to your calendar.
- Recurring events are expanded (`singleEvents=true`), so each occurrence reminds.
