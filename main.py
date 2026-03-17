"""AI Employee — entry point.

Supports both Cloud and Local zones via AGENT_ZONE env var.
Default: local (safe — full execution capabilities).

Usage:
    uv run python main.py                  # Local mode (default)
    uv run python main.py --zone cloud     # Cloud mode
    uv run python main.py --zone local     # Explicit local mode
    uv run python main.py --dry-run        # Dry run mode
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv("config/.env")

from backend.orchestrator.orchestrator import OrchestratorConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Employee")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--zone",
        choices=["cloud", "local"],
        default=None,
        help="Override AGENT_ZONE (default: from env or 'local')",
    )
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
    if args.zone:
        os.environ["AGENT_ZONE"] = args.zone

    zone = os.getenv("AGENT_ZONE", "local").lower()
    config = OrchestratorConfig.from_env()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    if zone == "cloud":
        from backend.cloud.cloud_orchestrator import CloudOrchestrator

        logger.info("Starting AI Employee — CLOUD zone")
        orchestrator = CloudOrchestrator(config)
    else:
        from backend.cloud.cloud_orchestrator import LocalOrchestrator

        logger.info("Starting AI Employee — LOCAL zone")
        orchestrator = LocalOrchestrator(config)

    try:
        asyncio.run(orchestrator.run())
    except KeyboardInterrupt:
        logger.info("AI Employee stopped")


if __name__ == "__main__":
    main()
