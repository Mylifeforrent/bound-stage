#!/usr/bin/env bash
# Shared shell helpers for the full-flow QA kit.  Source, do not execute.

set -euo pipefail

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$PKG_DIR/../../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
ENV_FILE="$PKG_DIR/.env.qa"
RUNTIME_DIR="$PKG_DIR/.runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_DIR="$RUNTIME_DIR/pids"
JENKINS_COMPOSE="$PKG_DIR/docker-compose.jenkins.yml"
PY="$BACKEND_DIR/.venv/bin/python"

mkdir -p "$LOG_DIR" "$PID_DIR"

say()  { printf '\033[1;36m[qa]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

load_env() {
  [ -f "$ENV_FILE" ] || die "missing $ENV_FILE; run: $PKG_DIR/qa.sh init"
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  : "${QA_API_PORT:?}" "${QA_WEB_PORT:?}" "${QA_IDP_PORT:?}" "${QA_MOCK_PORT:?}"
  : "${QA_JENKINS_PORT:?}" "${QA_BASE_URL:?}" "${QA_WEB_URL:?}" "${QA_JENKINS_URL:?}"
  : "${QA_TEST_DB_NAME:=huntai_test_qa}"
  export QA_TEST_DB_NAME
}

http_code() {
  curl -s -o /dev/null --max-time 2 -w '%{http_code}' "$1" 2>/dev/null || true
}

wait_http() {
  local url="$1" expected="${2:-200}" timeout="${3:-60}" label="${4:-$1}"
  local start now code
  start="$(date +%s)"
  while :; do
    code="$(http_code "$url")"
    if [ "$code" = "$expected" ]; then
      ok "$label"
      return 0
    fi
    now="$(date +%s)"
    if [ $((now - start)) -ge "$timeout" ]; then
      warn "$label did not return $expected within ${timeout}s (last: ${code:-no response})"
      return 1
    fi
    sleep 1
  done
}

pid_alive() {
  local pidfile="$1" pid
  [ -f "$pidfile" ] || return 1
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

start_bg() {
  local name="$1" cwd="$2"
  shift 2
  local pidfile="$PID_DIR/$name.pid" logfile="$LOG_DIR/$name.log"
  if pid_alive "$pidfile"; then
    ok "$name already running (pid $(cat "$pidfile"))"
    return 0
  fi
  : > "$logfile"
  (
    cd "$cwd"
    nohup "$@" >>"$logfile" 2>&1 &
    echo $! >"$pidfile"
  )
  sleep 1
  if pid_alive "$pidfile"; then
    ok "$name started (pid $(cat "$pidfile"), log $logfile)"
  else
    warn "$name exited immediately; tail of $logfile:"
    tail -n 20 "$logfile" || true
    return 1
  fi
}

stop_bg() {
  local name="$1"
  local pidfile="$PID_DIR/$name.pid"
  local pid
  if ! pid_alive "$pidfile"; then
    rm -f "$pidfile"
    return 0
  fi
  pid="$(cat "$pidfile")"
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pidfile"
  ok "$name stopped"
}

require_backend_venv() {
  [ -x "$PY" ] || die "backend venv missing; run: cd backend && uv sync"
}

require_node_modules() {
  [ -x "$FRONTEND_DIR/node_modules/.bin/vite" ] || die "frontend deps missing; run: cd frontend && npm install"
}

port_busy() {
  "$PY" - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.settimeout(0.4)
    sys.exit(0 if s.connect_ex(("127.0.0.1", port)) == 0 else 1)
PY
}
