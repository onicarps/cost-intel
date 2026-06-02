#!/usr/bin/env bash
# scripts/dogfood.sh — Ingest real Hermes cron logs and verify costs
set -euo pipefail

echo "=== cost-intel dogfood test ==="
echo ""

# Ensure latest pricing
echo "Refreshing model pricing..."
cost-intel refresh-pricing 2>/dev/null || echo "  (skipped — no API key)"
echo ""

# Ingest recent OpenRouter/Hermes logs if available
LOG_DIR="${HOME}/.hermes"
if [ -d "$LOG_DIR" ]; then
    echo "Checking for recent logs in $LOG_DIR..."
    find "$LOG_DIR" -name "*.jsonl" -mtime -1 2>/dev/null | head -5 | while read -r f; do
        echo "  Ingesting: $f"
        cost-intel ingest-api-responses "$f" --format openrouter --label "dogfood-$(basename "$f")" 2>/dev/null || echo "  (skipped)"
    done
    echo ""
fi

# Show cost report
echo "=== Cost Report (last 7 days) ==="
cost-intel report --last 7d --by-model
echo ""

# Budget status
echo "=== Budget Status ==="
cost-intel budget status
echo ""

echo "=== Dogfood complete ==="
