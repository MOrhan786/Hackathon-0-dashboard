# AI Employee Procfile
# Used by Railway, Render, and similar platforms

# Main orchestrator service (runs all watchers + action executor)
worker: uv run python -m backend.orchestrator

# Dashboard web server
web: uv run python -m backend.dashboard_server --host 0.0.0.0 --port $PORT
