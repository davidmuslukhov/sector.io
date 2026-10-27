#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

ENV_NAME=city3d

if ! command -v uv >/dev/null 2>&1; then
  echo "Could not find uv."
  echo "Install uv: https://docs.astral.sh/uv/getting-started/installation/"
  echo "Or: brew install uv"
  exit 1
fi

echo "Syncing ${ENV_NAME} environment with uv..."
uv sync

if command -v direnv >/dev/null 2>&1; then
  if [[ -f .envrc ]]; then
    direnv allow .
    echo
    echo "Environment ${ENV_NAME} is ready (direnv will activate .venv in this directory)."
  fi
else
  echo
  echo "Environment ${ENV_NAME} is ready."
  echo "Optional: brew install direnv, add 'eval \"\$(direnv hook zsh)\"' to ~/.zshrc, then re-enter this directory."
fi

echo "Launch the city with ./run_city.sh"
