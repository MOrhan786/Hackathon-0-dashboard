#!/usr/bin/env bash
cd /home/ubuntu/ai-employee
export PATH="$HOME/.local/bin:$PATH"
VAULT_PATH=./vault HEALTH_PORT=8080 uv run python cloud/health_monitor.py
