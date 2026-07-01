#!/bin/bash
#
# Runs ON the mini-pc (invoked by deploy.sh over SSH). Pulls code, installs
# dependencies, refreshes the systemd unit if it changed, and restarts the bot.

set -e

SERVICE="familybot.service"

echo "Current directory: $(pwd)"

echo "Pulling latest changes from git..."
git pull origin main

echo "Installing dependencies..."
uv sync

echo "Checking for systemd service file updates..."
if ! cmp -s "systemd/${SERVICE}" "/etc/systemd/system/${SERVICE}"; then
    echo "Systemd service file changed, updating..."
    sudo cp "systemd/${SERVICE}" "/etc/systemd/system/${SERVICE}"
    sudo systemctl daemon-reload
    echo "✓ Systemd service file updated"
else
    echo "Systemd service file unchanged"
fi

echo "Restarting ${SERVICE}..."
sudo systemctl restart "${SERVICE}"

echo "Status:"
# No sudo: reading status doesn't need root, and this avoids a password prompt for the
# --no-pager variant that isn't covered by the scoped sudoers rule.
systemctl --no-pager status "${SERVICE}" || true

echo "Update complete."
