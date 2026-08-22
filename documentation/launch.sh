#!/usr/bin/env bash
set -euo pipefail
pip install -r requirements.txt
mkdocs serve -a 0.0.0.0:8005
