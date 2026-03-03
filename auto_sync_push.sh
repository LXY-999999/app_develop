#!/bin/zsh
set -euo pipefail

SRC_DIR="/Users/luxiaoyue/Documents/lxy/code/tushuare_crawl"
DST_REPO="/Users/luxiaoyue/Documents/lxy/report_paper"

cd "$DST_REPO"

setopt null_glob
for f in $SRC_DIR/AI应用_concept_cons_sme_逐家AI深度分析_*.xlsx; do
  cp -f "$f" "$DST_REPO/"
done

if [[ -n "$(git status --porcelain)" ]]; then
  git add -A
  git commit -m "auto sync report_paper $(date '+%Y-%m-%d %H:%M:%S')"
  git push origin main
fi
