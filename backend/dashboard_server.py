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
from backend.mcp_servers.odoo.odoo_client import OdooClient
from backend.orchestrator.dashboard import (
    count_vault_files,
    get_action_log_counts,
    get_recent_done,
)

# Load .env from config directory
load_dotenv(dotenv_path=Path(__file__).parent.parent / "config" / ".env")

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


# ── Odoo API Endpoints ─────────────────────────────────────────────────────


def _get_odoo_client() -> OdooClient | None:
    """Create Odoo client from env vars. Returns None if not configured."""
    dev_mode = os.getenv("DEV_MODE", "true").lower() == "true"
    odoo_url = os.getenv("ODOO_URL", "")
    odoo_db = os.getenv("ODOO_DATABASE", "")
    odoo_user = os.getenv("ODOO_USERNAME", "")
    odoo_key = os.getenv("ODOO_API_KEY", "")

    if not odoo_url or not odoo_db:
        return None

    return OdooClient(
        url=odoo_url,
        db=odoo_db,
        username=odoo_user,
        api_key=odoo_key,
        dev_mode=dev_mode,
    )


@app.get("/api/odoo/invoices")
async def list_odoo_invoices(limit: int = 20, status: str = "posted") -> JSONResponse:
    """List invoices from Odoo."""
    client = _get_odoo_client()
    if not client:
        return JSONResponse(content={"error": "Odoo not configured", "invoices": []})

    try:
        if client._dev_mode:
            client._uid = 1
            invoices = client.list_invoices(limit=limit, status=status)
        else:
            client.authenticate()
            invoices = client.list_invoices(limit=limit, status=status)
        return JSONResponse(content={"invoices": invoices})
    except Exception as exc:
        logger.error("Error fetching Odoo invoices: %s", exc)
        return JSONResponse(content={"error": str(exc), "invoices": []})


@app.get("/api/odoo/customers")
async def list_odoo_customers(limit: int = 50, search: str = "") -> JSONResponse:
    """List customers from Odoo."""
    client = _get_odoo_client()
    if not client:
        return JSONResponse(content={"error": "Odoo not configured", "customers": []})

    try:
        if client._dev_mode:
            client._uid = 1
            customers = client.list_customers(search=search, limit=limit)
        else:
            client.authenticate()
            customers = client.list_customers(search=search, limit=limit)
        return JSONResponse(content={"customers": customers})
    except Exception as exc:
        logger.error("Error fetching Odoo customers: %s", exc)
        return JSONResponse(content={"error": str(exc), "customers": []})


@app.get("/api/odoo/transactions")
async def list_odoo_transactions(
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
) -> JSONResponse:
    """List transactions from Odoo."""
    client = _get_odoo_client()
    if not client:
        return JSONResponse(content={"error": "Odoo not configured", "transactions": []})

    try:
        if client._dev_mode:
            client._uid = 1
            transactions = client.list_transactions(date_from=date_from, date_to=date_to, limit=limit)
        else:
            client.authenticate()
            transactions = client.list_transactions(date_from=date_from, date_to=date_to, limit=limit)
        return JSONResponse(content={"transactions": transactions})
    except Exception as exc:
        logger.error("Error fetching Odoo transactions: %s", exc)
        return JSONResponse(content={"error": str(exc), "transactions": []})


@app.get("/api/odoo/account-balance")
async def get_odoo_account_balance(account_id: int = 1) -> JSONResponse:
    """Get account balance from Odoo."""
    client = _get_odoo_client()
    if not client:
        return JSONResponse(content={"error": "Odoo not configured", "balance": None})

    try:
        if client._dev_mode:
            client._uid = 1
            balance = client.get_account_balance(account_id)
        else:
            client.authenticate()
            balance = client.get_account_balance(account_id)
        return JSONResponse(content={"balance": balance})
    except Exception as exc:
        logger.error("Error fetching Odoo account balance: %s", exc)
        return JSONResponse(content={"error": str(exc), "balance": None})


@app.get("/api/odoo/summary")
async def get_odoo_summary() -> JSONResponse:
    """Get Odoo summary: total invoices, customers, and account balance."""
    client = _get_odoo_client()
    if not client:
        return JSONResponse(content={
            "error": "Odoo not configured",
            "total_invoices": 0,
            "total_customers": 0,
            "account_balance": 0,
        })

    try:
        if client._dev_mode:
            client._uid = 1
        else:
            client.authenticate()

        invoices = client.list_invoices(limit=100)
        customers = client.list_customers(limit=100)
        balance_data = client.get_account_balance(1)

        total_invoices = sum(inv["amount_total"] for inv in invoices)
        total_customers = len(customers)
        account_balance = balance_data.get("balance", 0)

        return JSONResponse(content={
            "total_invoices": total_invoices,
            "total_customers": total_customers,
            "account_balance": account_balance,
            "currency": balance_data.get("currency", "USD"),
        })
    except Exception as exc:
        logger.error("Error fetching Odoo summary: %s", exc)
        return JSONResponse(content={"error": str(exc), "total_invoices": 0, "total_customers": 0, "account_balance": 0})


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
