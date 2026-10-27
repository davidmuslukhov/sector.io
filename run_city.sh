#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python city.py "$@"
fi

echo "city3d is not installed. Run ./setup_env.sh first."
exit 1
