"""LinkedIn MCP Server — Posts content to LinkedIn automatically."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

load_dotenv("config/.env")

logger = logging.getLogger(__name__)

LINKEDIN_SESSION_PATH = os.getenv("LINKEDIN_SESSION_PATH", "config/linkedin_session")
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"


class LinkedInMCP:
    def __init__(self, session_path: str = None):
        self.session_path = Path(session_path or LINKEDIN_SESSION_PATH)
        self.dev_mode = DEV_MODE
        self.dry_run = DRY_RUN
        
    async def post(self, content: str) -> dict:
        logger.info(f"LinkedIn MCP: DEV_MODE={self.dev_mode}, DRY_RUN={self.dry_run}")
        
        if self.dev_mode or self.dry_run:
            logger.info(f"[DEV_MODE/DRY_RUN] Would post to LinkedIn: {content[:200]}...")
            return {"status": "dev_mode", "post_id": None, "url": None, "message": "DEV_MODE/DRY_RUN ON"}
        
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()
                if self.session_path.exists():
                    await context.storage_state(path=self.session_path / "storage.json")
                await page.goto("https://www.linkedin.com/feed/")
                start_box = await page.wait_for_selector("div[role=\"textbox\"]", timeout=10000)
                await start_box.click()
                await start_box.fill(content)
                post_button = await page.wait_for_selector("button:has-text(\"Post\")", timeout=10000)
                await post_button.click()
                await page.wait_for_selector("div[aria-label^=\"Post published\"]", timeout=5000)
                await browser.close()
                logger.info("LinkedIn post successful!")
                return {"status": "success", "post_id": datetime.now().isoformat(), "url": "https://www.linkedin.com/feed/", "message": "Published"}
        except Exception as e:
            logger.error(f"LinkedIn post failed: {e}")
            return {"status": "error", "post_id": None, "url": None, "message": str(e)}


async def process_approved_file(file_path: Path, linkedin_mcp: LinkedInMCP) -> bool:
    from backend.utils.frontmatter import parse_frontmatter
    try:
        fm = parse_frontmatter(file_path)
        post_type = fm.get("type", "")
        platform = fm.get("platform", "")
        if "linkedin" not in post_type.lower() and "linkedin" not in platform.lower():
            return False
        content = fm.get("content", "")
        if not content:
            content = file_path.read_text(encoding="utf-8").split("---", 2)[-1].strip()
        logger.info(f"Processing LinkedIn post: {file_path.name}")
        result = await linkedin_mcp.post(content)
        if result["status"] in ["success", "dev_mode"]:
            done_dir = file_path.parent.parent / "Done"
            done_dir.mkdir(parents=True, exist_ok=True)
            file_path.rename(done_dir / file_path.name)
            logger.info(f"Moved to Done/: {file_path.name}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return False


async def monitor_approved_folder(vault_path: Path, linkedin_mcp: LinkedInMCP):
    approved_dir = vault_path / "Approved"
    logger.info(f"Monitoring Approved folder: {approved_dir}")
    while True:
        try:
            if approved_dir.exists():
                for md_file in approved_dir.glob("*.md"):
                    try:
                        fm = parse_frontmatter(md_file)
                        if "linkedin" in fm.get("type", "").lower() or "linkedin" in fm.get("platform", "").lower():
                            logger.info(f"Found LinkedIn post: {md_file.name}")
                            await process_approved_file(md_file, linkedin_mcp)
                    except: pass
        except Exception as e:
            logger.error(f"Error in monitor loop: {e}")
        await asyncio.sleep(10)


def main():
    parser = argparse.ArgumentParser(description="LinkedIn MCP")
    parser.add_argument("--post", type=str)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--vault", type=Path, default=Path("./vault"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    linkedin_mcp = LinkedInMCP()
    if args.post:
        result = asyncio.run(linkedin_mcp.post(args.post))
        print(f"Result: {result}")
    elif args.file:
        success = asyncio.run(process_approved_file(args.file, linkedin_mcp))
        print(f"Success: {success}")
    elif args.monitor:
        asyncio.run(monitor_approved_folder(args.vault, linkedin_mcp))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
