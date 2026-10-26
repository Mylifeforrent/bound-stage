#!/usr/bin/env bash
# HuntAI Test · full-flow QA kit entry point.
#
#   ./backend/qa/full_flow/qa.sh init          # generate .env.qa, create DB, migrate, seed
#   ./backend/qa/full_flow/qa.sh up            # mock IdP + mock integrations + API + Vite
#   ./backend/qa/full_flow/qa.sh jenkins-up    # real Jenkins (Docker)
#   ./backend/qa/full_flow/qa.sh test-live     # existing live smoke suite
#   ./backend/qa/full_flow/qa.sh test-jenkins  # real Jenkins E2E
#   ./backend/qa/full_flow/qa.sh all           # init + up + jenkins-up + both live suites
#
# The kit is isolated: it uses .env.qa, a separate database and its own ports.
# It never prints or copies secret values.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib.sh
. "$SCRIPT_DIR/scripts/lib.sh"

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
  cat <<'EOF'

Other commands:
  status          show health of every QA process
  down            stop API / Vite / mocks started by this kit
  restart         down + up
  reset           truncate QA business data and reseed identity
  reset --hard    drop and recreate the QA database, then migrate + seed
  test-backend    ruff + mypy + pytest in backend/
  test-frontend   lint + tsc + build + vitest in frontend/
  test-all        backend + frontend + live smoke + Jenkins E2E
  jenkins-up      start Jenkins (add --no-build if the base image is unavailable)
  jenkins-down    stop Jenkins (keeps its volume)
  jenkins-reset   stop Jenkins and delete its volume
  ai-check        optional DeepSeek connectivity check (not used by product AI)
  logs [name]     tail a process log
  doctor          pre-flight environment check
EOF
}

cmd_init() {
  say "initialising isolated QA environment"
  if [ ! -x "$PY" ]; then
    say "backend venv missing; running uv sync"
    (cd "$BACKEND_DIR" && uv sync)
  fi
  require_backend_venv
  "$PY" "$SCRIPT_DIR/scripts/init_env.py" "$@"
  "$PY" "$SCRIPT_DIR/scripts/ensure_db.py"
  load_env
  say "applying migrations to $QA_DB_NAME"
  (cd "$BACKEND_DIR" && "$BACKEND_DIR/.venv/bin/alembic" upgrade head)
  say "seeding local identity / project / mock connectors"
  (cd "$BACKEND_DIR" && "$PY" scripts/seed_local_identity.py)
  ok "init complete"
}

cmd_up() {
  load_env
  require_backend_venv
  require_node_modules

  if ! port_busy "$QA_IDP_PORT"; then
    start_bg mock-idp "$BACKEND_DIR" "$PY" scripts/mock_idp.py
  else
    ok "mock IdP already listening on $QA_IDP_PORT"
  fi

  if ! port_busy "$QA_MOCK_PORT"; then
    start_bg mock-integrations "$BACKEND_DIR" "$PY" scripts/mock_integrations.py --port "$QA_MOCK_PORT"
  else
    ok "mock integrations already listening on $QA_MOCK_PORT (reusing)"
  fi

  if ! port_busy "$QA_API_PORT"; then
    # 0.0.0.0 so the Jenkins container can reach the API via host.docker.internal.
    start_bg api "$BACKEND_DIR" "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$QA_API_PORT"
  else
    ok "API already listening on $QA_API_PORT"
  fi

  if ! port_busy "$QA_WEB_PORT"; then
    HUNTAI_API_PROXY="$QA_BASE_URL" \
      start_bg web "$FRONTEND_DIR" "$FRONTEND_DIR/node_modules/.bin/vite" --port "$QA_WEB_PORT"
  else
    ok "Vite already listening on $QA_WEB_PORT"
  fi

  wait_http "http://127.0.0.1:$QA_IDP_PORT/.well-known/openid-configuration" 200 60 "mock IdP" || true
  wait_http "http://127.0.0.1:$QA_MOCK_PORT/healthz" 200 30 "mock integrations" || true
  wait_http "http://127.0.0.1:$QA_API_PORT/healthz" 200 60 "API liveness" || die "API did not start; see $LOG_DIR/api.log"
  wait_http "http://127.0.0.1:$QA_API_PORT/readyz" 200 30 "API readiness" || die "API cannot reach the DB; see $LOG_DIR/api.log"
  wait_http "$QA_WEB_URL/" 200 60 "frontend" || die "Vite did not start; see $LOG_DIR/web.log"

  cat <<EOF

$(ok "QA stack is up")
  UI             $QA_WEB_URL
  API            $QA_BASE_URL  (docs: $QA_BASE_URL/docs)
  mock IdP       http://127.0.0.1:$QA_IDP_PORT
  mock ints      http://127.0.0.1:$QA_MOCK_PORT
  accounts       local-dev-user / local-dev-user-2   (password: local-dev)
  reset data     $SCRIPT_DIR/qa.sh reset
  logs           $LOG_DIR

EOF
}

cmd_down() {
  stop_bg web || true
  stop_bg api || true
  stop_bg mock-integrations || true
  stop_bg mock-idp || true
  ok "QA stack stopped"
}

cmd_status() {
  load_env
  printf '%-18s %-38s %s\n' "component" "url" "status"
  printf '%-18s %-38s %s\n' "------------------" "--------------------------------------" "------"
  local api_code idp_code mock_code web_code
  api_code="$(http_code "$QA_BASE_URL/healthz")"
  idp_code="$(http_code "http://127.0.0.1:$QA_IDP_PORT/.well-known/openid-configuration")"
  mock_code="$(http_code "http://127.0.0.1:$QA_MOCK_PORT/healthz")"
  web_code="$(http_code "$QA_WEB_URL/")"
  printf '%-18s %-38s %s\n' "API" "$QA_BASE_URL/healthz" "${api_code:-down}"
  printf '%-18s %-38s %s\n' "mock IdP" "http://127.0.0.1:$QA_IDP_PORT" "${idp_code:-down}"
  printf '%-18s %-38s %s\n' "mock integrations" "http://127.0.0.1:$QA_MOCK_PORT" "${mock_code:-down}"
  printf '%-18s %-38s %s\n' "frontend" "$QA_WEB_URL" "${web_code:-down}"
  local j_code
  j_code="$(http_code "$QA_JENKINS_URL/job/full-flow-smoke/api/json")"
  printf '%-18s %-38s %s\n' "Jenkins" "$QA_JENKINS_URL" "${j_code:-down}"
  echo
  for pidfile in "$PID_DIR"/*.pid; do
    [ -e "$pidfile" ] || continue
    printf '%-22s pid %s\n' "$(basename "$pidfile" .pid)" "$(cat "$pidfile")"
  done
}

cmd_reset() {
  load_env
  if [ "${1:-}" = "--hard" ]; then
    cmd_down
    say "dropping and recreating $QA_DB_NAME"
    "$PY" - "$ENV_FILE" "$SCRIPT_DIR/scripts" <<'PY'
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[2])
from _qa_env import admin_dsn, database_name, parse_env

values = parse_env(Path(sys.argv[1]))
url = values["DATABASE_URL"]
name = database_name(url)

async def main() -> None:
    import asyncpg
    conn = await asyncpg.connect(admin_dsn(url))
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            name,
        )
        quoted = '"' + name.replace('"', '""') + '"'
        await conn.execute(f"DROP DATABASE IF EXISTS {quoted}")
        await conn.execute(f"CREATE DATABASE {quoted}")
    finally:
        await conn.close()
    print(f"[ok] recreated database {name}")

asyncio.run(main())
PY
    (cd "$BACKEND_DIR" && "$BACKEND_DIR/.venv/bin/alembic" upgrade head)
    (cd "$BACKEND_DIR" && "$PY" scripts/seed_local_identity.py)
    ok "hard reset complete"
    return
  fi
  "$PY" "$SCRIPT_DIR/scripts/ensure_db.py" >/dev/null
  (cd "$BACKEND_DIR" && "$PY" scripts/reset_local_data.py --yes)
  ok "business data reset; identity seed restored"
}

cmd_test_backend() {
  load_env
  require_backend_venv
  "$PY" "$SCRIPT_DIR/scripts/ensure_db.py" >/dev/null
  local test_url
  test_url="$("$PY" - "$ENV_FILE" "$SCRIPT_DIR/scripts" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[2])
from _qa_env import parse_env, replace_database

values = parse_env(Path(sys.argv[1]))
name = values.get("QA_TEST_DB_NAME") or "huntai_test_qa"
print(replace_database(values["DATABASE_URL"], name))
PY
)"
  # The repository suite TRUNCATEs every table; point it at the dedicated
  # huntai_test_qa database, never at the running QA stack or the developer's
  # own huntai_test database.
  (cd "$BACKEND_DIR" && \
    DATABASE_URL="$test_url" \
    uv run ruff check . && \
    uv run ruff format --check . && \
    uv run mypy app && \
    DATABASE_URL="$test_url" uv run pytest)
}

cmd_test_frontend() {
  require_node_modules
  (cd "$FRONTEND_DIR" && npm run lint && npx tsc --noEmit && npm run build && npm run test)
}

cmd_test_live() {
  load_env
  require_backend_venv
  echo "This suite creates its own cases/environments and drives the real API."
  (cd "$BACKEND_DIR" && \
    HUNTAI_LIVE=1 \
    HUNTAI_BASE_URL="$QA_BASE_URL" \
    HUNTAI_SESSION_COOKIE="$SESSION_COOKIE_NAME" \
    HUNTAI_WEBHOOK_SECRET="$GITHUB_WEBHOOK_SECRET" \
    GITHUB_WEBHOOK_SECRET="$GITHUB_WEBHOOK_SECRET" \
    "$PY" -m pytest tests/test_live_smoke.py -q)
}

cmd_test_jenkins() {
  load_env
  require_backend_venv
  (cd "$BACKEND_DIR" && "$PY" "$SCRIPT_DIR/scripts/run_jenkins_e2e.py")
}

cmd_jenkins_up() {
  load_env
  command -v docker >/dev/null || die "docker not found"
  docker info >/dev/null 2>&1 || die "Docker daemon is not running"
  local build_flag="--build"
  if [ "${1:-}" = "--no-build" ]; then
    build_flag="--no-build"
    say "starting Jenkins without rebuilding (uses the local image)"
  else
    say "building and starting Jenkins on $QA_JENKINS_URL"
  fi
  if ! docker compose -f "$JENKINS_COMPOSE" --env-file "$ENV_FILE" up -d "$build_flag"; then
    # Offline / registry-mirror failures are common; an already-built local
    # image is still a valid test double.  Make the fallback explicit.
    if [ "$build_flag" = "--build" ] && \
       docker image inspect huntai-qa-jenkins-jenkins:latest >/dev/null 2>&1; then
      warn "build failed; falling back to the existing local image (--no-build)"
      warn "fix the Docker registry/Dockerfile if you need a reproducible rebuild"
      docker compose -f "$JENKINS_COMPOSE" --env-file "$ENV_FILE" up -d --no-build
    else
      die "Jenkins could not be started; see the build output above"
    fi
  fi
  wait_http "$QA_JENKINS_URL/login" 200 180 "Jenkins login" || true
  wait_http "$QA_JENKINS_URL/job/full-flow-smoke/api/json" 200 120 "Jenkins job full-flow-smoke" || \
    die "Jenkins did not expose the seeded job; see: docker compose -f $JENKINS_COMPOSE logs jenkins"
  ok "Jenkins is ready: $QA_JENKINS_URL"
}

cmd_jenkins_down() {
  load_env
  docker compose -f "$JENKINS_COMPOSE" --env-file "$ENV_FILE" down
  ok "Jenkins stopped (volume kept)"
}

cmd_jenkins_reset() {
  load_env
  docker compose -f "$JENKINS_COMPOSE" --env-file "$ENV_FILE" down -v
  ok "Jenkins stopped and its volume deleted"
}

cmd_logs() {
  local name="${1:-api}"
  tail -n 100 -f "$LOG_DIR/$name.log"
}

cmd_ai_check() {
  load_env
  require_backend_venv
  "$PY" "$SCRIPT_DIR/scripts/ai_check.py"
}

cmd_all() {
  cmd_init
  cmd_up
  cmd_jenkins_up
  cmd_test_live
  cmd_test_jenkins
}

COMMAND="${1:-}"
[ $# -gt 0 ] && shift || true
case "$COMMAND" in
  init) cmd_init "$@" ;;
  up) cmd_up ;;
  down) cmd_down ;;
  restart) cmd_down; cmd_up ;;
  status) cmd_status ;;
  reset) cmd_reset "$@" ;;
  test-backend) cmd_test_backend ;;
  test-frontend) cmd_test_frontend ;;
  test-live) cmd_test_live ;;
  test-jenkins) cmd_test_jenkins ;;
  test-all) cmd_test_backend; cmd_test_frontend; cmd_test_live; cmd_test_jenkins ;;
  jenkins-up) cmd_jenkins_up "$@" ;;
  jenkins-down) cmd_jenkins_down ;;
  jenkins-reset) cmd_jenkins_reset ;;
  ai-check) cmd_ai_check ;;
  logs) cmd_logs "$@" ;;
  doctor) require_backend_venv; "$PY" "$SCRIPT_DIR/scripts/doctor.py" ;;
  ""|-h|--help|help) usage ;;
  *) die "unknown command: $COMMAND (try --help)" ;;
esac
