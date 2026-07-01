#!/bin/bash
#
# Deploy from your desktop: push to GitHub, then SSH to the mini-pc and update.
# Usage: ./deploy.sh
#
# Prerequisites (one-time, see docs/deployment.md):
#   - SSH key copied to the mini-pc (ssh-copy-id) so no password is asked.
#   - NOPASSWD sudoers entry for systemctl so the restart needs no password.

set -e

REMOTE_HOST="10.0.0.181"
REMOTE_USER="pdesjardins"
REMOTE_DIR="/home/pdesjardins/code/python-discord-family-bot"

echo "Pushing to GitHub..."
git push origin main

echo "Deploying to ${REMOTE_HOST}..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" "cd ${REMOTE_DIR} && bash -l deployment/update.sh"

echo ""
echo "Deploy complete!"
