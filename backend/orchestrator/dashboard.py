"""Dashboard renderer — generates vault/Dashboard.md from orchestrator state.

Pure functions for rendering, with atomic file writing for safe Obsidian updates.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from backend.orchestrator.watchdog import WatcherInfo

logger = logging.getLogger(__name__)


@dataclass
class DashboardState:
    """Snapshot of the orchestrator's current state for dashboard rendering."""

    watchers: list[WatcherInfo] = field(default_factory=list)
    vault_counts: dict[str, int] = field(default_factory=dict)
    dev_mode: bool = True
    last_update: str = ""
    uptime_seconds: int = 0
    errors: list[str] = field(default_factory=list)
    recent_done: list[str] = field(default_factory=list)
    action_log_counts: dict[str, int] = field(default_factory=dict)


def count_vault_files(vault_path: str | Path) -> dict[str, int]:
    """Count .md files in each vault subfolder.

    Returns:
        Dict mapping folder names to file counts.
    """
    vault = Path(vault_path)
    folders = [
        "Inbox",
        "Needs_Action",
        "Plans",
        "Pending_Approval",
        "Approved",
        "Rejected",
        "Done",
    ]

    counts: dict[str, int] = {}
    for folder in folders:
        folder_path = vault / folder
        if folder_path.exists():
            counts[folder] = len(list(folder_path.glob("*.md")))
        else:
            counts[folder] = 0

    return counts


def get_recent_done(vault_path: str | Path, limit: int = 5) -> list[str]:
    """Return filenames from vault/Done/, sorted by mtime descending.

    Args:
        vault_path: Path to vault root.
        limit: Maximum number of filenames to return.

    Returns:
        List of filenames (most recent first).
    """
    done_dir = Path(vault_path) / "Done"
    if not done_dir.exists():
        return []

    md_files = list(done_dir.glob("*.md"))
    md_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return [f.name for f in md_files[:limit]]


def get_action_log_counts(vault_path: str | Path, days: int = 7) -> dict[str, int]:
    """Count email and social post actions from recent action logs.

    Reads vault/Logs/actions/*.json files from the last N days.
    JSON format: {"date":"...","entries":[{"action_type":"..."}]}

    Args:
        vault_path: Path to vault root.
        days: Number of days to look back.

    Returns:
        Dict with keys "emails" and "social", each an int count.
    """
    import json
    from datetime import date, timedelta

    log_dir = Path(vault_path) / "Logs" / "actions"
    counts = {"emails": 0, "social": 0}

    if not log_dir.exists():
        return counts

    cutoff = date.today() - timedelta(days=days)

    for json_file in log_dir.glob("*.json"):
        try:
            # Extract date from filename (format: actions-YYYY-MM-DD.json)
            name = json_file.stem
            date_part = name.replace("actions-", "")
            try:
                file_date = date.fromisoformat(date_part)
                if file_date < cutoff:
                    continue
            except ValueError:
                pass  # If date can't be parsed from name, include the file

            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                entries = data
            else:
                entries = data.get("entries", [])

            for entry in entries:
                action_type = entry.get("action_type", "")
                if action_type.startswith("email"):
                    counts["emails"] += 1
                elif "_post" in action_type or action_type.startswith("social"):
                    counts["social"] += 1
        except (json.JSONDecodeError, OSError):
            continue

    return counts


def render_dashboard(state: DashboardState) -> str:
    """Pure function: render DashboardState to a markdown string.

    Args:
        state: Current orchestrator state snapshot.

    Returns:
        Complete markdown content for Dashboard.md.
    """
    lines: list[str] = []

    # Header
    mode_badge = "DEV MODE" if state.dev_mode else "PRODUCTION"
    lines.append(f"# AI Employee Dashboard [{mode_badge}]")
    lines.append("")
    lines.append(f"**Last Updated**: {state.last_update}")
    lines.append(f"**Uptime**: {_format_uptime(state.uptime_seconds)}")
    lines.append("")

    # Quick Stats
    total_files = sum(state.vault_counts.values())
    pending = state.vault_counts.get("Needs_Action", 0) + state.vault_counts.get("Pending_Approval", 0)
    done = state.vault_counts.get("Done", 0)
    emails = state.action_log_counts.get("emails", 0)
    social = state.action_log_counts.get("social", 0)
    lines.append("> [!info] Quick Stats")
    lines.append(f"> **{total_files}** vault files | **{pending}** pending | **{done}** done | **{emails}** emails | **{social}** social posts (7d)")
    lines.append("")

    # Briefing sentinel block
    lines.append("<!-- BRIEFING_SECTION_START -->")
    lines.append("<!-- BRIEFING_SECTION_END -->")
    lines.append("")

    # System Health
    error_count = len(state.errors)
    running_count = sum(1 for w in state.watchers if w.status == "running")
    total_watchers = len(state.watchers)
    if error_count == 0 and running_count == total_watchers and total_watchers > 0:
        lines.append("> [!success] System Health")
        lines.append(f"> All {running_count} watchers operational. No errors detected.")
    elif error_count > 0:
        lines.append("> [!warning] System Health")
        lines.append(f"> {error_count} error(s) detected. {running_count}/{total_watchers} watchers running.")
    else:
        lines.append("> [!info] System Health")
        lines.append(f"> {running_count}/{total_watchers} watchers running.")
    lines.append("")

    # Watcher Status Table
    lines.append("## Watcher Status")
    lines.append("")
    if state.watchers:
        lines.append("| Watcher | Status | Restarts | Last Error | Started |")
        lines.append("|---------|--------|----------|------------|---------|")
        for w in state.watchers:
            status_icon = _status_icon(w.status)
            error = (w.last_error or "—")[:60]
            started = w.started_at or "—"
            lines.append(
                f"| {w.name} | {status_icon} {w.status} | {w.restart_count} | {error} | {started} |"
            )
    else:
        lines.append("*No watchers configured.*")
    lines.append("")

    # Vault Status with internal links
    lines.append("## Vault Status")
    lines.append("")
    lines.append("| Folder | Files |")
    lines.append("|--------|-------|")
    for folder, count in state.vault_counts.items():
        lines.append(f"| [[{folder}]] | {count} |")
    lines.append("")

    # Recent Activity
    if state.recent_done:
        lines.append("## Recent Activity")
        lines.append("")
        for filename in state.recent_done:
            stem = filename.replace(".md", "")
            lines.append(f"- [[Done/{stem}]]")
        lines.append("")

    # Errors
    if state.errors:
        lines.append("## Recent Errors")
        lines.append("")
        for err in state.errors:
            lines.append(f"- {err}")
        lines.append("")

    # Navigation
    lines.append("## Navigation")
    lines.append("")
    lines.append("- [[Business_Goals]] | [[Content_Strategy]] | [[Company_Handbook]]")
    lines.append("- [[Briefings]] | [[Plans]] | [[Done]]")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("*Auto-generated by AI Employee Orchestrator. Do not edit manually.*")

    return "\n".join(lines)


async def write_dashboard(vault_path: str | Path, content: str) -> None:
    """Write dashboard content atomically via temp file + os.replace.

    This ensures Obsidian never reads a partially-written file.
    """
    vault = Path(vault_path)
    dashboard_path = vault / "Dashboard.md"

    # Write to temp file in same directory (required for atomic rename)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(vault),
        prefix=".dashboard-",
        suffix=".tmp",
    )
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.replace(tmp_path, str(dashboard_path))
        logger.debug("Dashboard updated: %s", dashboard_path)
    except Exception:
        os.close(fd) if not os.get_inheritable(fd) else None  # noqa: B018
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _format_uptime(seconds: int) -> str:
    """Format uptime seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m"


def _status_icon(status: str) -> str:
    """Return an icon for the watcher status."""
    icons = {
        "running": "🟢",
        "stopped": "⚪",
        "error": "🟡",
        "failed": "🔴",
        "pending": "⏳",
    }
    return icons.get(status, "❓")
