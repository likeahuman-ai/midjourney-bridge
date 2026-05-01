#!/usr/bin/env bash
# Run every quality gate with clear summary output.
#
# Usage:
#   ./scripts/check.sh              # standard gates: lint, format, types, unit tests
#   ./scripts/check.sh --integration  # also run integration tests (hits real MJ — needs MJ_COOKIE)
#   ./scripts/check.sh --quick      # skip mypy (slowest gate) for fast iteration

set -euo pipefail

cd "$(dirname "$0")/.."

# --- arg parsing -------------------------------------------------------------
INTEGRATION=0
QUICK=0
for arg in "$@"; do
    case "$arg" in
        --integration|-i) INTEGRATION=1 ;;
        --quick|-q)       QUICK=1 ;;
        --help|-h)
            sed -n '2,8p' "$0"
            exit 0
            ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

# --- pretty print ------------------------------------------------------------
HR="────────────────────────────────────────────────────────────────────"
G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; B='\033[1;34m'; N='\033[0m'

step() { printf "\n${B}▸ %s${N}\n${HR}\n" "$1"; }
ok()   { printf "${G}✓ %s${N}\n" "$1"; }
fail() { printf "${R}✗ %s${N}\n" "$1"; FAILED=1; }

FAILED=0

# --- gates -------------------------------------------------------------------

step "ruff lint"
if uv run ruff check src/ tests/; then ok "ruff lint clean"; else fail "ruff lint"; fi

step "ruff format check"
if uv run ruff format --check src/ tests/; then ok "format clean"; else fail "format"; fi

if [[ $QUICK -eq 0 ]]; then
    step "mypy --strict"
    if uv run mypy src/midjourney_bridge; then ok "mypy clean"; else fail "mypy"; fi
fi

step "pytest (unit)"
if uv run pytest -q -m "not integration"; then ok "unit tests passed"; else fail "unit tests"; fi

if [[ $INTEGRATION -eq 1 ]]; then
    step "pytest (integration — hits real MJ)"
    if [[ -z "${MJ_COOKIE:-}" ]] && [[ ! -f "$(uv run python -c 'from midjourney_bridge.session import env_path; print(env_path())')" ]]; then
        echo -e "${Y}⚠  no MJ session configured — run \`mj cookie auto\` first${N}"
        fail "integration tests"
    elif uv run pytest -q -m integration --override-ini="addopts="; then
        ok "integration tests passed"
    else
        fail "integration tests"
    fi
fi

# --- summary -----------------------------------------------------------------
echo
echo "$HR"
if [[ $FAILED -eq 0 ]]; then
    printf "${G}✓ all gates passed${N}\n"
    exit 0
else
    printf "${R}✗ at least one gate failed${N}\n"
    exit 1
fi
