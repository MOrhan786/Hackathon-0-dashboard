"""Health monitor — lightweight HTTP server reporting system status.

Exposes /health endpoint on port 8080 for uptime monitoring.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

logger = logging.getLogger(__name__)

VAULT_PATH = Path(os.getenv("VAULT_PATH", "./vault"))
PORT = int(os.getenv("HEALTH_PORT", "8080"))


def get_health_status() -> dict:
    now = datetime.now(timezone.utc)

    pm2_status = "unknown"
    try:
        result = subprocess.run(
            ["pm2", "jlist"], capture_output=True, text=True, timeout=5
        )
        processes = json.loads(result.stdout)
        pm2_status = {p["name"]: p["pm2_env"]["status"] for p in processes}
    except Exception:
        pm2_status = "pm2 not available"

    folder_counts = {}
    for folder in ["Needs_Action", "Pending_Approval", "Approved", "Done", "In_Progress"]:
        p = VAULT_PATH / folder
        if p.exists():
            folder_counts[folder] = len(list(p.rglob("*.md")))

    return {
        "status": "healthy",
        "timestamp": now.isoformat(),
        "agent_zone": os.getenv("AGENT_ZONE", "unknown"),
        "dev_mode": os.getenv("DEV_MODE", "unknown"),
        "pm2_processes": pm2_status,
        "vault_folders": folder_counts,
    }


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            status = get_health_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status, indent=2).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info("Health monitor running on port %d", PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
