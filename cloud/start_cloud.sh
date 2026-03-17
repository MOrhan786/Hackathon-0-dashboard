#!/usr/bin/env bash
cd /home/ubuntu/ai-employee
export PATH="$HOME/.local/bin:$PATH"
AGENT_ZONE=cloud uv run python cloud/cloud_main.py
