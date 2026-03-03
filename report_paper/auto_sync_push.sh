#!/bin/zsh
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

SRC_DIR="/Users/luxiaoyue/Documents/lxy/report_paper"
REPO_DIR="/Users/luxiaoyue/Documents/lxy/.app_develop_repo"
REMOTE_URL="https://github.com/LXY-999999/app_develop.git"
SUBDIR="report_paper"
BRANCH="main"

if [[ ! -d "$REPO_DIR/.git" ]]; then
  rm -rf "$REPO_DIR"
  git clone "$REMOTE_URL" "$REPO_DIR"
fi

git -C "$REPO_DIR" config user.name "LXY-999999"
git -C "$REPO_DIR" config user.email "LXY-999999@users.noreply.github.com"

# keep local mirror repo aligned first
git -C "$REPO_DIR" fetch origin "$BRANCH"
git -C "$REPO_DIR" checkout "$BRANCH"
git -C "$REPO_DIR" pull --rebase origin "$BRANCH"

mkdir -p "$REPO_DIR/$SUBDIR"

# mirror whole source folder into repo/report_paper
rsync -a --delete \
  --exclude ".git/" \
  --exclude ".DS_Store" \
  "$SRC_DIR/" "$REPO_DIR/$SUBDIR/"

status_out=$(git -C "$REPO_DIR" status --porcelain)
if [[ -n "$status_out" ]]; then
  git -C "$REPO_DIR" add -A
  git -C "$REPO_DIR" commit -m "sync report_paper folder $(date "+%Y-%m-%d %H:%M:%S")"
  git -C "$REPO_DIR" push origin "$BRANCH"
fi
