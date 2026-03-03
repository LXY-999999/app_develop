#!/bin/zsh
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

SRC_DIR="/Users/luxiaoyue/Documents/lxy/code/tushuare_crawl"
DST_REPO="/Users/luxiaoyue/Documents/lxy/report_paper"

cd "$DST_REPO"

setopt null_glob
for f in $SRC_DIR/AI应用_concept_cons_sme_逐家AI深度分析_AI*.xlsx; do
  /bin/cp -f "$f" "$DST_REPO/"
done

if [[ -n "$(/usr/bin/git status --porcelain)" ]]; then
  /usr/bin/git add -A
  /usr/bin/git commit -m "auto sync report_paper $(/bin/date '+%Y-%m-%d %H:%M:%S')"
  /usr/bin/git push origin main
fi
