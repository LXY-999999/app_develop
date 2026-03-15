#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESUME_PATH="${1:-${SCRIPT_DIR}/tmp/dummy_resume.txt}"
PHONE_NUMBER="${PHONE_NUMBER:-15558333981}"
RECOVERY_ATTEMPTS="${RECOVERY_ATTEMPTS:-4}"
CANDIDATE_TRIALS="${CANDIDATE_TRIALS:-5}"
PER_COMPANY_TIMEOUT="${PER_COMPANY_TIMEOUT:-240}"

COMPANIES=(
  "字节跳动"
  "腾讯"
  "阿里巴巴"
  "百度"
  "京东"
  "美团"
  "快手"
  "网易"
  "小米"
  "华为"
)

ARGS=()
for company in "${COMPANIES[@]}"; do
  ARGS+=(--company "${company}")
done

ARGS+=(
  --job-keyword "多模态"
  --job-keyword "多模态大模型"
  --phone "${PHONE_NUMBER}"
  --resume "${RESUME_PATH}"
  --name "Test"
  --email "test@example.com"
  --headless
  --max-recovery-attempts "${RECOVERY_ATTEMPTS}"
  --max-candidate-trials "${CANDIDATE_TRIALS}"
  --per-company-timeout "${PER_COMPANY_TIMEOUT}"
)

exec "${SCRIPT_DIR}/.venv/bin/python" "${SCRIPT_DIR}/run_cli.py" "${ARGS[@]}"
