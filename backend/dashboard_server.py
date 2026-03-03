"""Real-time dashboard server — FastAPI + WebSocket for live vault state.

Run with: uv run python -m backend.dashboard_server
Serves on: http://localhost:8765
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.briefing.data_collectors import DataCollectors
from backend.orchestrator.dashboard import (
    count_vault_files,
    get_action_log_counts,
    get_recent_done,
)

load_dotenv()

logger = logging.getLogger(__name__)

VAULT_PATH = Path(os.getenv("VAULT_PATH", "./vault"))
HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
PORT = int(os.getenv("DASHBOARD_PORT", "8765"))

app = FastAPI(title="AI Employee Dashboard")


def _build_state() -> dict:
    """Collect current vault state into a JSON-serializable dict."""
    vault_counts = count_vault_files(VAULT_PATH)
    recent_done = get_recent_done(VAULT_PATH, limit=10)
    action_log_counts = get_action_log_counts(VAULT_PATH, days=7)

    # Revenue from business goals
    goals = DataCollectors.collect_business_goals(VAULT_PATH)
    revenue_target = goals.monthly_revenue_target if goals else None
    # MTD revenue comes from Odoo; use a safe fallback for the dashboard
    revenue_mtd: float = 0
    if goals and goals.key_results:
        for kr in goals.key_results:
            if "revenue" in kr.metric.lower() or "mrr" in kr.metric.lower():
                # Try to parse current value
                import re

                numeric = re.sub(r"[^\d.]", "", kr.current or "")
                if numeric:
                    try:
                        revenue_mtd = float(numeric)
                    except ValueError:
                        pass
                break

    total_files = sum(vault_counts.values())
    pending = vault_counts.get("Needs_Action", 0) + vault_counts.get("Pending_Approval", 0)

    return {
        "vault_counts": vault_counts,
        "recent_done": recent_done,
        "action_log_counts": action_log_counts,
        "revenue": {
            "mtd": revenue_mtd,
            "target": revenue_target or 0,
        },
        "total_files": total_files,
        "pending": pending,
        "completed": vault_counts.get("Done", 0),
        "last_update": datetime.now(UTC).isoformat(),
    }


# ── HTTP Routes ──────────────────────────────────────────────────────────────


@app.get("/")
async def serve_dashboard() -> FileResponse:
    """Serve the interactive HTML dashboard."""
    html_path = VAULT_PATH / "dashboard.html"
    if not html_path.exists():
        return FileResponse(
            path=str(VAULT_PATH.parent / "vault" / "dashboard.html"),
            media_type="text/html",
        )
    return FileResponse(path=str(html_path), media_type="text/html")


@app.get("/api/state")
async def get_state() -> JSONResponse:
    """Return current vault state as JSON."""
    state = _build_state()
    return JSONResponse(content=state)


# ── Approve / Reject API ─────────────────────────────────────────────────────


class ActionRequest(BaseModel):
    filename: str


@app.get("/api/pending")
async def list_pending() -> JSONResponse:
    """List all files in Pending_Approval with preview."""
    pending_dir = VAULT_PATH / "Pending_Approval"
    files = []
    if pending_dir.exists():
        for f in sorted(pending_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            content = f.read_text(encoding="utf-8")
            files.append({
                "filename": f.name,
                "size": len(content),
                "preview": content[:500],
                "full_content": content,
            })
    return JSONResponse(content={"files": files, "count": len(files)})


@app.get("/api/file/{folder}/{filename}")
async def read_file(folder: str, filename: str) -> JSONResponse:
    """Read a vault file's full content."""
    allowed = {"Pending_Approval", "Needs_Action", "Plans", "Approved", "Rejected", "Done", "Inbox"}
    if folder not in allowed:
        return JSONResponse(content={"error": "Invalid folder"}, status_code=400)
    file_path = VAULT_PATH / folder / filename
    if not file_path.exists():
        return JSONResponse(content={"error": "File not found"}, status_code=404)
    content = file_path.read_text(encoding="utf-8")
    return JSONResponse(content={"filename": filename, "folder": folder, "content": content})


@app.post("/api/approve")
async def approve_file(req: ActionRequest) -> JSONResponse:
    """Update frontmatter status to 'approved' and move to Approved/."""
    from backend.utils.frontmatter import update_frontmatter

    src = VAULT_PATH / "Pending_Approval" / req.filename
    dst = VAULT_PATH / "Approved" / req.filename
    if not src.exists():
        return JSONResponse(content={"error": "File not found in Pending_Approval"}, status_code=404)
    # Update frontmatter so ActionExecutor picks it up
    try:
        update_frontmatter(src, {"status": "approved"})
    except Exception:
        logger.warning("Could not update frontmatter on %s", req.filename)
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    logger.info("APPROVED: %s -> Approved/", req.filename)
    return JSONResponse(content={"status": "approved", "filename": req.filename})


@app.post("/api/reject")
async def reject_file(req: ActionRequest) -> JSONResponse:
    """Move file from Pending_Approval to Rejected."""
    src = VAULT_PATH / "Pending_Approval" / req.filename
    dst = VAULT_PATH / "Rejected" / req.filename
    if not src.exists():
        return JSONResponse(content={"error": "File not found in Pending_Approval"}, status_code=404)
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    logger.info("REJECTED: %s -> Rejected/", req.filename)
    return JSONResponse(content={"status": "rejected", "filename": req.filename})


# ── WebSocket ────────────────────────────────────────────────────────────────

connected_clients: set[WebSocket] = set()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Push live vault state to connected clients every 5 seconds."""
    await websocket.accept()
    connected_clients.add(websocket)
    logger.info("WebSocket client connected (%d total)", len(connected_clients))
    try:
        # Send initial state immediately
        state = _build_state()
        await websocket.send_text(json.dumps(state))

        # Then push updates every 5 seconds
        while True:
            await asyncio.sleep(5)
            state = _build_state()
            await websocket.send_text(json.dumps(state))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WebSocket error: %s", exc)
    finally:
        connected_clients.discard(websocket)
        logger.info("WebSocket client disconnected (%d remaining)", len(connected_clients))


# ── Entrypoint ───────────────────────────────────────────────────────────────


def main() -> None:
    """Start the dashboard server."""
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Starting AI Employee Dashboard at http://%s:%d", HOST, PORT)
    logger.info("Vault path: %s", VAULT_PATH.resolve())
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
