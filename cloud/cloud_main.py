"""Cloud VM entry point for the AI Employee.

Usage:
    AGENT_ZONE=cloud uv run python cloud/cloud_main.py
    AGENT_ZONE=cloud uv run python cloud/cloud_main.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv("config/.env")

os.environ["AGENT_ZONE"] = "cloud"

from backend.cloud.cloud_orchestrator import CloudOrchestrator
from backend.orchestrator.orchestrator import OrchestratorConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Employee — Cloud Agent")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    config = OrchestratorConfig.from_env()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    logger = logging.getLogger(__name__)
    logger.info("Starting AI Employee CLOUD Agent")
    logger.info("DEV_MODE=%s, DRY_RUN=%s, ZONE=cloud", config.dev_mode, config.dry_run)

    orchestrator = CloudOrchestrator(config)
    try:
        asyncio.run(orchestrator.run())
    except KeyboardInterrupt:
        logger.info("Cloud agent stopped by user")


if __name__ == "__main__":
    main()
