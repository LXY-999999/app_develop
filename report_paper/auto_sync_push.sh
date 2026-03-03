#!/bin/zsh
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

REPO_DIR="/Users/luxiaoyue/Documents/lxy/report_paper"
BRANCH="main"

# Sync whole folder as a repo snapshot
status_out=$(/usr/bin/git -C "$REPO_DIR" status --porcelain)
if [[ -n "$status_out" ]]; then
  /usr/bin/git -C "$REPO_DIR" add -A
  /usr/bin/git -C "$REPO_DIR" commit -m "sync report_paper folder $(/bin/date "+%Y-%m-%d %H:%M:%S")"
  /usr/bin/git -C "$REPO_DIR" push origin "$BRANCH"
fi
