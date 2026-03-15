#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  exec "${SCRIPT_DIR}/.venv/bin/python" "${SCRIPT_DIR}/run_cli.py" --help
fi

RESUME_PATH="${1:-${SCRIPT_DIR}/tmp/dummy_resume.txt}"
KEEP_OPEN_SECONDS="${KEEP_OPEN_SECONDS:-120}"
PHONE_NUMBER="${PHONE_NUMBER:-15558333981}"

ARGS=(
  --company "阿里巴巴"
  --job-keyword "多模态"
  --phone "${PHONE_NUMBER}"
  --resume "${RESUME_PATH}"
  --name "Test"
  --email "test@example.com"
  --max-recovery-attempts 6
  --max-candidate-trials 6
)

if [[ "${HEADLESS:-0}" == "1" ]]; then
  ARGS+=(--headless)
else
  ARGS+=(--keep-open --keep-open-seconds "${KEEP_OPEN_SECONDS}")
fi

exec "${SCRIPT_DIR}/.venv/bin/python" "${SCRIPT_DIR}/run_cli.py" "${ARGS[@]}"
