#!/usr/bin/env bash
# scripts/bootstrap.sh — One-command setup for cost-intel development
set -euo pipefail

VENV_DIR="${VENV_DIR:-${HOME}/.venvs/cost-intel}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== cost-intel bootstrap ==="
echo "  Project: $PROJECT_DIR"
echo "  Venv:    $VENV_DIR"
echo ""

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate and install
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip
pip install -e "${PROJECT_DIR}"
pip install pytest ruff pytest-cov 2>/dev/null || true

echo ""
echo "=== Running tests ==="
cd "$PROJECT_DIR"
pytest tests/ -v --tb=short
echo ""
echo "=== Bootstrap complete ==="
echo "  Run: source ${VENV_DIR}/bin/activate"
echo "  Run: cost-intel --help"
