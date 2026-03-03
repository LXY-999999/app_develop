#!/bin/zsh
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

SRC_DIR="/Users/luxiaoyue/Documents/lxy/code/tushuare_crawl"
DST_REPO="/Users/luxiaoyue/Documents/lxy/report_paper"

cd /

setopt null_glob
for f in $SRC_DIR/AI应用_concept_cons_sme_逐家AI深度分析_AI*.xlsx; do
  /bin/cp -f "$f" "$DST_REPO/"
done

status_out=$(/usr/bin/git -C "$DST_REPO" status --porcelain)
if [[ -n "$status_out" ]]; then
  /usr/bin/git -C "$DST_REPO" add -A
  /usr/bin/git -C "$DST_REPO" commit -m "auto sync report_paper $(/bin/date '+%Y-%m-%d %H:%M:%S')"
  /usr/bin/git -C "$DST_REPO" push origin main
fi
