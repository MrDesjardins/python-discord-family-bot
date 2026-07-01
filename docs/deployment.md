# Deployment

Code lives on GitHub. You deploy from your **desktop** with one command; it pushes to
GitHub and tells the **Ubuntu mini-pc** to pull, install, and restart — no passwords.

```
desktop:  ./deploy.sh
            ├─ git push origin main
            └─ ssh pdesjardins@10.0.0.181  ── deployment/update.sh
                                                  ├─ git pull
                                                  ├─ uv sync
                                                  ├─ copy systemd unit if changed
                                                  └─ sudo systemctl restart familybot.service
```

Adjust `REMOTE_HOST` / `REMOTE_USER` / `REMOTE_DIR` at the top of `deploy.sh` if needed.

## One-time mini-pc setup (Ubuntu)

```bash
# 1. Install uv (package manager) for the deploy user
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone the repo to the path used by deploy.sh / the systemd unit
mkdir -p ~/code && cd ~/code
git clone git@github.com:<you>/python-discord-family-bot.git
cd python-discord-family-bot
uv sync

# 3. Create the runtime config (NOT in git)
cp .env.example .env                 # fill in BOT_TOKEN, OPENAI_API_KEY, GOOGLE_SERVICE_ACCOUNT_FILE
cp config.example.yaml config.yaml   # fill in guild_id + channel IDs
# copy your Google service-account JSON here too (see docs/google-setup.md)

# 4. Install the systemd service
sudo cp systemd/familybot.service /etc/systemd/system/familybot.service
sudo systemctl daemon-reload
sudo systemctl enable --now familybot.service
sudo systemctl status familybot.service
```

The unit sets `WorkingDirectory` to the project folder, so the bot reads `./.env` and
`./config.yaml` from there (and `ENV=prod` selects `BOT_TOKEN`).

## Passwordless deploy

### a) SSH without a password (from the desktop)

```bash
ssh-keygen -t ed25519            # if you don't already have a key
ssh-copy-id pdesjardins@10.0.0.181
ssh pdesjardins@10.0.0.181 'echo ok'   # should print ok with no password
```

### b) `sudo systemctl` without a password (on the mini-pc)

`deploy.sh` must restart the service non-interactively. Add a scoped sudoers rule:

```bash
sudo visudo -f /etc/sudoers.d/familybot
```

```sudoers
pdesjardins ALL=(root) NOPASSWD: /usr/bin/systemctl restart familybot.service, \
    /usr/bin/systemctl daemon-reload, \
    /usr/bin/cp systemd/familybot.service /etc/systemd/system/familybot.service, \
    /usr/bin/systemctl status familybot.service
```

(Run `which systemctl cp` to confirm the paths on your machine.)

## Operating

```bash
sudo systemctl status familybot.service     # is it running?
journalctl -u familybot.service -f          # live logs (also app.log in the project dir)
sudo systemctl restart familybot.service    # manual restart
```

## Updating dependencies

Edit `pyproject.toml`, run `uv sync` locally to refresh `uv.lock`, commit the lockfile,
then `./deploy.sh` (the mini-pc runs `uv sync`).
