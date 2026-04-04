#!/usr/bin/env bash

set -euo pipefail

TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${OPENCLAW_TINKER_ENV_FILE:-${TOOLS_DIR}/.env}"
REPO_DIR="${OPENCLAW_RL_REPO_DIR:-${TOOLS_DIR}/OpenClaw-RL}"
VENV_DIR="${OPENCLAW_TINKER_VENV_DIR:-${TOOLS_DIR}/.venv}"
PYTHON_BIN="${OPENCLAW_TINKER_PYTHON:-python3}"
REPO_REF="${OPENCLAW_RL_REF:-main}"
AUTO_UPDATE="${OPENCLAW_RL_AUTO_UPDATE:-0}"
SKIP_INSTALL="${OPENCLAW_TINKER_SKIP_INSTALL:-0}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

METHOD="${OPENCLAW_METHOD:-combine}"
MODEL_NAME="${OPENCLAW_MODEL_NAME:-Qwen/Qwen3.5-4B}"
BATCH_SIZE="${OPENCLAW_BATCH_SIZE:-8}"
MAX_STEPS="${OPENCLAW_MAX_STEPS:-1000}"
PRM_M="${OPENCLAW_PRM_M:-1}"
TRAIN_EPOCHS="${OPENCLAW_TRAIN_EPOCHS:-2}"
W_OPD="${OPENCLAW_W_OPD:-1.0}"
W_RL="${OPENCLAW_W_RL:-1.0}"
LEARNING_RATE="${OPENCLAW_LEARNING_RATE:-1e-4}"
LOSS_FN="${OPENCLAW_LOSS_FN:-ppo}"
PROXY_HOST="${OPENCLAW_PROXY_HOST:-127.0.0.1}"
PROXY_PORT="${OPENCLAW_PROXY_PORT:-30000}"
WANDB_DISABLED="${WANDB_DISABLED:-1}"
WANDB_PROJECT="${WANDB_PROJECT:-openclaw-tinker}"

if [[ -z "${OPENCLAW_SERVED_MODEL_NAME:-}" ]]; then
  case "${MODEL_NAME}" in
    *3.5*4B*|*35*4B*)
      SERVED_MODEL_NAME="qwen3.5-4b-tinker"
      ;;
    *8B*)
      SERVED_MODEL_NAME="qwen3-8b-tinker"
      ;;
    *4B*)
      SERVED_MODEL_NAME="qwen3-4b-tinker"
      ;;
    *)
      SERVED_MODEL_NAME="openclaw-tinker"
      ;;
  esac
else
  SERVED_MODEL_NAME="${OPENCLAW_SERVED_MODEL_NAME}"
fi

print_banner() {
  cat <<EOF
OpenClaw Tinker launcher
  Repo: ${REPO_DIR}
  Venv: ${VENV_DIR}
  Method: ${METHOD}
  Model: ${MODEL_NAME}
  Served model name: ${SERVED_MODEL_NAME}
  Proxy: http://${PROXY_HOST}:${PROXY_PORT}/v1
EOF
}

require_api_key() {
  if [[ -z "${TINKER_API_KEY:-}" ]]; then
    echo "Missing TINKER_API_KEY." >&2
    echo "Copy ${TOOLS_DIR}/env.example to ${TOOLS_DIR}/.env and fill it in, or export TINKER_API_KEY first." >&2
    exit 1
  fi
}

ensure_repo() {
  if [[ ! -d "${REPO_DIR}/.git" ]]; then
    git clone --depth 1 --branch "${REPO_REF}" https://github.com/Gen-Verse/OpenClaw-RL.git "${REPO_DIR}"
    return
  fi

  if [[ "${AUTO_UPDATE}" == "1" ]]; then
    git -C "${REPO_DIR}" fetch origin "${REPO_REF}" --depth 1
    git -C "${REPO_DIR}" checkout "${REPO_REF}"
    git -C "${REPO_DIR}" pull --ff-only origin "${REPO_REF}"
  fi
}

ensure_venv() {
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi

  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"

  if [[ "${SKIP_INSTALL}" == "1" ]]; then
    return
  fi

  python -m pip install --upgrade pip setuptools wheel
  python -m pip install \
    tinker \
    fastapi \
    "uvicorn[standard]" \
    transformers \
    torch \
    sentencepiece \
    safetensors \
    wandb
}

run_openclaw() {
  cd "${REPO_DIR}/openclaw-tinker"
  export WANDB_DISABLED
  export WANDB_PROJECT
  export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"

  exec python run.py \
    --method "${METHOD}" \
    --model-name "${MODEL_NAME}" \
    --batch-size "${BATCH_SIZE}" \
    --max-steps "${MAX_STEPS}" \
    --learning-rate "${LEARNING_RATE}" \
    --loss-fn "${LOSS_FN}" \
    --prm-m "${PRM_M}" \
    --train-epochs "${TRAIN_EPOCHS}" \
    --w-opd "${W_OPD}" \
    --w-rl "${W_RL}" \
    --proxy-host "${PROXY_HOST}" \
    --proxy-port "${PROXY_PORT}" \
    --served-model-name "${SERVED_MODEL_NAME}" \
    --wandb-project "${WANDB_PROJECT}" \
    "$@"
}

main() {
  require_api_key
  ensure_repo
  ensure_venv
  print_banner
  run_openclaw "$@"
}

main "$@"
