#!/usr/bin/env bash
# Chạy pipeline cho cả ba quy trình mẫu; kết quả nằm trong outputs/<tên quy trình>/
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src python -m text2bpmn_mining data/bpmn/*.bpmn --n-rep "${N_REP:-10}" --out outputs
