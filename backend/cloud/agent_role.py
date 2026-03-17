"""Agent role configuration for Cloud vs Local deployment.

Defines work zones and their capabilities.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class AgentZone(str, Enum):
    """Work zone enumeration."""
    CLOUD = "cloud"
    LOCAL = "local"


@dataclass
class AgentCapabilities:
    """Capabilities for a work zone."""
    can_watch_gmail: bool = False
    can_watch_whatsapp: bool = False
    can_watch_facebook: bool = False
    can_watch_linkedin: bool = False
    can_watch_twitter: bool = False
    can_execute_actions: bool = False
    can_process_approvals: bool = False


ZONE_CAPABILITIES: dict[AgentZone, AgentCapabilities] = {
    AgentZone.CLOUD: AgentCapabilities(
        can_watch_gmail=True,
        can_watch_whatsapp=False,
        can_watch_facebook=True,
        can_watch_linkedin=True,
        can_watch_twitter=True,
        can_execute_actions=False,
        can_process_approvals=False,
    ),
    AgentZone.LOCAL: AgentCapabilities(
        can_watch_gmail=True,
        can_watch_whatsapp=True,
        can_watch_facebook=True,
        can_watch_linkedin=True,
        can_watch_twitter=True,
        can_execute_actions=True,
        can_process_approvals=True,
    ),
}


def get_capabilities(zone: AgentZone) -> AgentCapabilities:
    """Get capabilities for a zone."""
    return ZONE_CAPABILITIES.get(zone, AgentCapabilities())


def get_current_zone() -> AgentZone:
    """Get current zone from environment."""
    zone = os.getenv("AGENT_ZONE", "local").lower()
    return AgentZone(zone) if zone in ["cloud", "local"] else AgentZone.LOCAL


class ClaimManager:
    """Manages file claiming for multi-agent coordination."""
    
    def __init__(self, vault_path: Path, agent_name: str) -> None:
        self.vault_path = vault_path
        self.agent_name = agent_name
    
    @property
    def in_progress_dir(self) -> Path:
        return self.vault_path / "In_Progress" / self.agent_name
    
    def claim(self, source_file: Path) -> Path | None:
        """Claim a file for processing."""
        in_progress_root = self.vault_path / "In_Progress"
        if in_progress_root.exists():
            for agent_dir in in_progress_root.iterdir():
                if agent_dir.is_dir():
                    claimed = agent_dir / source_file.name
                    if claimed.exists():
                        return None
        self.in_progress_dir.mkdir(parents=True, exist_ok=True)
        dest = self.in_progress_dir / source_file.name
        try:
            source_file.rename(dest)
            return dest
        except (OSError, FileNotFoundError):
            return None
    
    def release(self, file_path: Path, destination: Path) -> Path:
        """Release a file to destination."""
        destination.mkdir(parents=True, exist_ok=True)
        dest = destination / file_path.name
        file_path.rename(dest)
        return dest
    
    def list_claimed(self) -> list[Path]:
        """List claimed files."""
        if not self.in_progress_dir.exists():
            return []
        return list(self.in_progress_dir.glob("*.md"))
