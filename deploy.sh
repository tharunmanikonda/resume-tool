#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REVISION="${1:-$(git -C "$ROOT_DIR" rev-parse HEAD)}"

APP_DIR="${APP_DIR:-$ROOT_DIR}" exec "$ROOT_DIR/ops/deploy_server.sh" "$REVISION"
