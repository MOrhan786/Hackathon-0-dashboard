"""Cloud Orchestrator — runs 24/7 on the Cloud VM.

Starts only the watchers and reasoning tasks that Cloud is allowed to run.
Writes drafts to Pending_Approval/, Plans/, and Updates/.
Never executes final send/post actions.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from backend.cloud.agent_role import (
    AgentZone,
    ClaimManager,
    get_capabilities,
    get_current_zone,
)
from backend.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
from backend.utils.timestamps import now_iso

logger = logging.getLogger(__name__)


class CloudOrchestrator(Orchestrator):
    """Extended orchestrator that respects Work-Zone boundaries."""

    def __init__(self, config: OrchestratorConfig) -> None:
        super().__init__(config)
        self.zone = get_current_zone()
        self.capabilities = get_capabilities(self.zone)
        self.claim_manager = ClaimManager(
            vault_path=self.vault_path,
            agent_name=self.zone.value,
        )
        (self.vault_path / "In_Progress" / "cloud").mkdir(parents=True, exist_ok=True)
        (self.vault_path / "In_Progress" / "local").mkdir(parents=True, exist_ok=True)
        (self.vault_path / "Updates").mkdir(parents=True, exist_ok=True)

    def _start_watchers(self) -> None:
        """Only start watchers this zone is allowed to run.

        IMPORTANT: _build_watcher_configs() returns list[tuple[str, callable]]
        where each item is (name, factory_function). NOT dicts.
        """
        watchers_config = self._build_watcher_configs()
        filtered = []

        for name, factory in watchers_config:
            name_lower = name.lower()
            allowed = False

            if "gmail" in name_lower and self.capabilities.can_watch_gmail:
                allowed = True
            elif "whatsapp" in name_lower and self.capabilities.can_watch_whatsapp:
                allowed = True
            elif "facebook" in name_lower and self.capabilities.can_watch_facebook:
                allowed = True
            elif "linkedin" in name_lower and self.capabilities.can_watch_linkedin:
                allowed = True
            elif "twitter" in name_lower and self.capabilities.can_watch_twitter:
                allowed = True
            elif "vault" in name_lower:
                allowed = True  # Vault watcher runs on all zones

            if allowed:
                filtered.append((name, factory))
            else:
                logger.info(
                    "[%s] Skipping watcher %s — not allowed in this zone",
                    self.zone.value,
                    name,
                )

        # Start the filtered watchers using the same logic as parent
        from backend.orchestrator.watchdog import WatcherTask
        for name, factory in filtered:
            try:
                watcher = factory()
                wt = WatcherTask(
                    name=name,
                    watcher=watcher,
                    max_restarts=self.config.max_restart_attempts,
                    log_dir=self.log_dir,
                )
                wt.start()
                self.watcher_tasks.append(wt)
                logger.info("[%s] Started watcher: %s", self.zone.value, name)
            except ImportError as exc:
                logger.warning("[%s] Skipping watcher %s: %s", self.zone.value, name, exc)
            except Exception:
                logger.exception("[%s] Failed to start watcher %s", self.zone.value, name)

        if not self.watcher_tasks:
            logger.warning("[%s] No watchers started", self.zone.value)

    def _start_action_executor(self) -> None:
        """Cloud: only process draft actions. Local: normal execution."""
        if self.zone == AgentZone.CLOUD:
            logger.info("[cloud] Action executor: draft-only mode")
            self._action_executor_task = asyncio.get_event_loop().create_task(
                self._cloud_draft_loop()
            )
        else:
            super()._start_action_executor()

    async def _cloud_draft_loop(self) -> None:
        """Cloud-specific: process Needs_Action items into drafts."""
        while True:
            try:
                needs_action = self.vault_path / "Needs_Action"
                if needs_action.exists():
                    for md_file in sorted(needs_action.glob("*.md")):
                        claimed = self.claim_manager.claim(md_file)
                        if claimed is None:
                            continue
                        logger.info("[cloud] Claimed: %s", md_file.name)
                        await self._process_cloud_item(claimed)
            except Exception:
                logger.exception("[cloud] Error in draft loop")
            await asyncio.sleep(self.config.check_interval)

    async def _process_cloud_item(self, file_path: Path) -> None:
        """Process a claimed item — create signal and move to Pending_Approval."""
        from backend.utils.frontmatter import parse_frontmatter
        try:
            fm = parse_frontmatter(file_path)
            item_type = fm.get("type", "unknown")
            timestamp = now_iso().replace(":", "-")
            signal_path = (
                self.vault_path / "Updates"
                / f"signal_{timestamp}_{file_path.stem}.md"
            )
            signal_path.write_text(
                f"---\n"
                f"type: cloud_signal\n"
                f"source: {file_path.name}\n"
                f"item_type: {item_type}\n"
                f"timestamp: {now_iso()}\n"
                f"status: drafted\n"
                f"---\n"
                f"Cloud processed {file_path.name} ({item_type})\n",
                encoding="utf-8",
            )
            pending = self.vault_path / "Pending_Approval"
            self.claim_manager.release(file_path, pending)
            logger.info("[cloud] Drafted and moved to Pending_Approval: %s", file_path.name)
        except Exception:
            logger.exception("[cloud] Failed to process: %s", file_path.name)


class LocalOrchestrator(CloudOrchestrator):
    """Local orchestrator — handles approvals, WhatsApp, and final execution.

    Extends CloudOrchestrator to add:
    - Signal merging from Updates/ into Dashboard
    - Full action execution capabilities
    """

    def __init__(self, config: OrchestratorConfig) -> None:
        super().__init__(config)
        self._signal_merge_task = None

    def _start_watchers(self) -> None:
        """Start all watchers for local mode."""
        # Local can run all watchers
        watchers_config = self._build_watcher_configs()
        
        from backend.orchestrator.watchdog import WatcherTask
        for name, factory in watchers_config:
            try:
                watcher = factory()
                wt = WatcherTask(
                    name=name,
                    watcher=watcher,
                    max_restarts=self.config.max_restart_attempts,
                    log_dir=self.log_dir,
                )
                wt.start()
                self.watcher_tasks.append(wt)
                logger.info("[local] Started watcher: %s", name)
            except ImportError as exc:
                logger.warning("[local] Skipping watcher %s: %s", name, exc)
            except Exception:
                logger.exception("[local] Failed to start watcher %s", name)

    def _start_action_executor(self) -> None:
        """Local: full execution mode + signal merging."""
        super()._start_action_executor()
        self._signal_merge_task = asyncio.get_event_loop().create_task(
            self._merge_cloud_signals()
        )

    async def _merge_cloud_signals(self) -> None:
        """Merge cloud signals from Updates/ into Dashboard."""
        while True:
            try:
                updates_dir = self.vault_path / "Updates"
                if updates_dir.exists():
                    signals = sorted(updates_dir.glob("signal_*.md"))
                    if signals:
                        dashboard = self.vault_path / "Dashboard.md"
                        existing = (
                            dashboard.read_text(encoding="utf-8")
                            if dashboard.exists() else ""
                        )
                        new_entries = []
                        for sig in signals:
                            from backend.utils.frontmatter import parse_frontmatter
                            fm = parse_frontmatter(sig)
                            ts = fm.get("timestamp", "?")
                            item = fm.get("item_type", "?")
                            source = fm.get("source", "?")
                            new_entries.append(f"- [{ts}] Cloud processed: {source} ({item})")
                        if new_entries:
                            activity = "\n".join(new_entries)
                            if "## Recent Activity" in existing:
                                existing = existing.replace(
                                    "## Recent Activity",
                                    f"## Recent Activity\n{activity}",
                                )
                            else:
                                existing += f"\n\n## Recent Activity\n{activity}\n"
                            dashboard.write_text(existing, encoding="utf-8")
                        done = self.vault_path / "Done"
                        done.mkdir(parents=True, exist_ok=True)
                        for sig in signals:
                            sig.rename(done / sig.name)
                        logger.info("[local] Merged %d cloud signals into Dashboard", len(signals))
            except Exception:
                logger.exception("[local] Error merging updates")
            await asyncio.sleep(60)
