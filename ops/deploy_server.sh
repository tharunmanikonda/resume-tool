#!/usr/bin/env bash
set -Eeuo pipefail

REVISION="${1:-}"
APP_DIR="${APP_DIR:-/home/resume-tool}"
REPO_URL="${REPO_URL:-https://github.com/tharunmanikonda/resume-tool.git}"
WEB_SERVICE="${WEB_SERVICE:-resume-tool-web.service}"
MCP_SERVICE="${MCP_SERVICE:-resume-tool-mcp.service}"
SERVICE_USER="${RESUME_SERVICE_USER:-$(id -un)}"
LOCK_FILE="${DEPLOY_LOCK_FILE:-/tmp/resume-tool-deploy.lock}"

if [[ -z "$REVISION" ]]; then
  echo "Usage: deploy_server.sh <git-commit>"
  exit 2
fi

if [[ "$APP_DIR" =~ [[:space:]] ]]; then
  echo "APP_DIR cannot contain spaces: $APP_DIR"
  exit 2
fi

for command in git python3 node npm curl flock systemctl sed; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required server command: $command"
    exit 1
  fi
done

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=()
else
  if ! command -v sudo >/dev/null 2>&1; then
    echo "Deployments by a non-root user require sudo for systemd updates."
    exit 1
  fi
  SUDO=(sudo)
fi

NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
if (( NODE_MAJOR < 20 )); then
  echo "Node.js 20 or newer is required; found $(node --version)."
  exit 1
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another resume deployment is already running."
  exit 1
fi

log() {
  printf '[deploy] %s\n' "$*"
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts="${3:-30}"
  local delay="${4:-2}"
  local attempt
  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null; then
      log "$name is healthy."
      return 0
    fi
    sleep "$delay"
  done
  echo "$name did not become healthy at $url"
  return 1
}

install_runtime() {
  if [[ ! -x .venv/bin/python ]]; then
    log "Creating the Python virtual environment."
    python3 -m venv .venv
  fi
  log "Installing Python dependencies."
  .venv/bin/python -m pip install \
    --disable-pip-version-check \
    --quiet \
    -r requirements.txt

  log "Installing locked frontend dependencies."
  npm ci --no-audit --no-fund --silent
  log "Building the web app and browser extension."
  npm run build

  log "Checking Python entry points without starting background workers."
  RESUME_DISABLE_EXTENSION_WORKER=1 .venv/bin/python -c \
    'import app; import resume_mcp.server'
}

install_service_units() {
  local web_tmp mcp_tmp
  web_tmp="$(mktemp)"
  mcp_tmp="$(mktemp)"
  sed \
    -e "s|__APP_DIR__|$APP_DIR|g" \
    -e "s|__SERVICE_USER__|$SERVICE_USER|g" \
    ops/systemd/resume-tool-web.service >"$web_tmp"
  sed \
    -e "s|__APP_DIR__|$APP_DIR|g" \
    -e "s|__SERVICE_USER__|$SERVICE_USER|g" \
    -e "s|__WEB_SERVICE__|$WEB_SERVICE|g" \
    ops/systemd/resume-tool-mcp.service >"$mcp_tmp"
  "${SUDO[@]}" install -m 0644 "$web_tmp" "/etc/systemd/system/$WEB_SERVICE"
  "${SUDO[@]}" install -m 0644 "$mcp_tmp" "/etc/systemd/system/$MCP_SERVICE"
  rm -f "$web_tmp" "$mcp_tmp"
  "${SUDO[@]}" systemctl daemon-reload
  "${SUDO[@]}" systemctl enable "$WEB_SERVICE" "$MCP_SERVICE" >/dev/null
}

restart_and_verify() {
  log "Restarting $WEB_SERVICE."
  "${SUDO[@]}" systemctl restart "$WEB_SERVICE"
  wait_for_url "Resume web service" "http://127.0.0.1:5001/health"

  log "Restarting $MCP_SERVICE."
  "${SUDO[@]}" systemctl restart "$MCP_SERVICE"
  wait_for_url "Resume MCP service" "http://127.0.0.1:8010/health"
}

rollback() {
  local exit_code=$?
  trap - ERR
  if [[ -n "${PREVIOUS_REVISION:-}" && "${CHECKOUT_CHANGED:-0}" -eq 1 ]]; then
    echo "Deployment failed. Rolling back to $PREVIOUS_REVISION."
    set +e
    (
      set -e
      git checkout --force "$PREVIOUS_REVISION"
      install_runtime
      install_service_units
      restart_and_verify
    )
    local rollback_code=$?
    set -e
    if [[ "$rollback_code" -ne 0 ]]; then
      echo "Automatic rollback also failed. Check systemd logs immediately."
    else
      echo "Rollback completed successfully."
    fi
  fi
  exit "$exit_code"
}
trap rollback ERR

if [[ ! -d "$APP_DIR/.git" ]]; then
  log "Cloning the repository into $APP_DIR."
  mkdir -p "$(dirname "$APP_DIR")"
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
PREVIOUS_REVISION="$(git rev-parse HEAD 2>/dev/null || true)"
CHECKOUT_CHANGED=0

log "Fetching commit $REVISION."
git fetch --prune origin
git cat-file -e "${REVISION}^{commit}"
git checkout --force "$REVISION"
CHECKOUT_CHANGED=1

if [[ ! -f .env ]]; then
  echo "Missing $APP_DIR/.env. Deployment will not create or replace production secrets."
  exit 1
fi

install_runtime
install_service_units
restart_and_verify

CHECKOUT_CHANGED=0
trap - ERR
log "Deployment complete at $(git rev-parse --short HEAD)."
