#!/bin/bash
# trigger-scan.sh — Trigger the Hourly Scan workflow on GitHub Actions
# Usage: ./scripts/trigger-scan.sh [--watch]
#   --watch  Stream logs after triggering

set -e

gh workflow run "Hourly Scan"
echo "✅ Workflow triggered."

if [ "$1" = "--watch" ]; then
    echo "Waiting for run to appear..."
    sleep 3
    gh run watch
fi
