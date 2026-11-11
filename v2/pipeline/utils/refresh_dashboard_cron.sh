#!/bin/bash
# Daily cron entry point: keeps the extraction-status dashboard live even when
# no pipeline run has happened (pipeline.py only regenerates+deploys it as a
# side effect of backfill/incremental/etc runs).
set -euo pipefail

export PATH="/opt/homebrew/bin:$PATH"

V2_DIR="/Users/saumay/Code/personal/projects/kvizzing/kvizzing_group/KVizzing-app/v2"
cd "$V2_DIR"

python3 pipeline/utils/backlog_report.py
python3 pipeline/utils/deploy_dashboard.py
