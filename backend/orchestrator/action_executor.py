"""Action executor — polls vault/Approved/ and dispatches approved actions.

Reads frontmatter from approval files to determine the action type, then
routes to the appropriate handler (email_send, email_reply, linkedin_post).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.utils.frontmatter import extract_frontmatter, update_frontmatter
from backend.utils.logging_utils import log_action
from backend.utils.timestamps import now_iso
from backend.utils.uuid_utils import correlation_id

if TYPE_CHECKING:
    from backend.orchestrator.orchestrator import OrchestratorConfig

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Polls vault/Approved/ and dispatches approved actions by type."""

    HANDLERS: dict[str, str] = {
        "email_send": "_handle_email_send",
        "email_reply": "_handle_email_reply",
        "linkedin_post": "_handle_linkedin_post",
        "linkedin_reply": "_handle_linkedin_reply",
        "whatsapp_reply": "_handle_whatsapp_reply",
        "facebook_post": "_handle_facebook_post",
        "instagram_post": "_handle_instagram_post",
        "twitter_post": "_handle_twitter_post",
    }

    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config
        self.vault_path = Path(config.vault_path)
        self.approved_dir = self.vault_path / "Approved"
        self.done_dir = self.vault_path / "Done"
        self.log_dir = self.vault_path / "Logs" / "actions"
        self._gmail_client: Any = None
        self._rate_limiter: Any = None

    async def run(self) -> None:
        """Polling loop — scan Approved folder every check_interval seconds."""
        logger.info("Action executor watching %s", self.approved_dir)
        while True:
            try:
                await self._process_cycle()
            except asyncio.CancelledError:
                logger.info("Action executor stopped")
                return
            except Exception:
                logger.exception("Error in action executor cycle")
            await asyncio.sleep(self.config.check_interval)

    async def _process_cycle(self) -> None:
        """Single scan + process cycle."""
        files = self._scan_approved()
        for file_path, frontmatter in files:
            await self.process_file(file_path, frontmatter)

    def _scan_approved(self) -> list[tuple[Path, dict[str, Any]]]:
        """List .md files in vault/Approved/ with parsed frontmatter."""
        if not self.approved_dir.exists():
            return []

        results: list[tuple[Path, dict[str, Any]]] = []
        for md_file in sorted(self.approved_dir.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
                fm, _ = extract_frontmatter(content)
                if fm and fm.get("status") == "approved":
                    results.append((md_file, fm))
            except (OSError, UnicodeDecodeError):
                logger.warning("Failed to read approval file: %s", md_file)
        return results

    async def process_file(self, file_path: Path, fm: dict[str, Any]) -> bool:
        """Process a single approval file. Returns True on success."""
        action_type = fm.get("type", "")
        cid = correlation_id()

        logger.info("Processing: %s (type=%s)", file_path.name, action_type)

        # DEV_MODE — log and move to Done
        if self.config.dev_mode:
            return await self._handle_dev_mode(file_path, fm, cid)

        # Look up handler
        handler_name = self.HANDLERS.get(action_type)
        if not handler_name:
            logger.warning("Unknown action type '%s' in %s — skipping", action_type, file_path.name)
            self._log_event(
                cid, "action_skipped", file_path.name, "failure", f"Unknown type: {action_type}"
            )
            return False

        handler = getattr(self, handler_name)

        try:
            await handler(file_path, fm, cid)
            # Skip _move_to_done() if the handler (e.g. LinkedInPoster) already moved the file
            if file_path.exists():
                self._move_to_done(file_path)
            else:
                logger.debug(
                    "File already moved by handler — skipping executor move: %s",
                    file_path.name,
                )
            self._log_event(
                cid, "action_executed", file_path.name, "success", f"type={action_type}"
            )
            logger.info("Completed: %s → vault/Done/", file_path.name)
            return True
        except Exception as exc:
            logger.exception("Failed to execute %s: %s", file_path.name, exc)
            self._log_event(cid, "action_failed", file_path.name, "failure", str(exc)[:200])
            return False

    # ── Handlers ─────────────────────────────────────────────────

    async def _handle_email_send(self, file_path: Path, fm: dict[str, Any], _cid: str) -> None:
        """Send email using GmailClient + RateLimiter."""
        client = self._get_gmail_client()
        rate_limiter = self._get_rate_limiter()

        # Rate limit check
        allowed, wait = rate_limiter.check()
        if not allowed:
            raise RuntimeError(f"Rate limit exceeded, wait {wait}s")

        to = fm.get("to", "")
        subject = fm.get("subject", "")
        # Read body from file content (after frontmatter)
        content = file_path.read_text(encoding="utf-8")
        _, body_text = extract_frontmatter(content)
        body = self._extract_email_body(body_text)

        if not to or not subject:
            raise ValueError(f"Missing required fields: to={to!r}, subject={subject!r}")

        # Send via asyncio.to_thread (GmailClient is synchronous)
        await asyncio.to_thread(client.authenticate)
        result = await asyncio.to_thread(client.send_message, to, subject, body)
        rate_limiter.record_send()

        logger.info("Email sent to %s (message_id=%s)", to, result.get("id", "?"))

    async def _handle_email_reply(self, file_path: Path, fm: dict[str, Any], _cid: str) -> None:
        """Reply to an email thread using GmailClient."""
        client = self._get_gmail_client()
        rate_limiter = self._get_rate_limiter()

        allowed, wait = rate_limiter.check()
        if not allowed:
            raise RuntimeError(f"Rate limit exceeded, wait {wait}s")

        thread_id = fm.get("thread_id", "")
        message_id = fm.get("message_id", "")
        content = file_path.read_text(encoding="utf-8")
        _, body_text = extract_frontmatter(content)
        body = self._extract_email_body(body_text)

        if not thread_id:
            raise ValueError(f"Missing thread_id in {file_path.name}")

        await asyncio.to_thread(client.authenticate)
        result = await asyncio.to_thread(client.reply_to_thread, thread_id, message_id, body)
        rate_limiter.record_send()

        logger.info("Reply sent (thread=%s, message_id=%s)", thread_id, result.get("id", "?"))

    async def _handle_linkedin_post(self, file_path: Path, _fm: dict[str, Any], _cid: str) -> None:
        """Publish an approved LinkedIn post via LinkedInPoster.

        LinkedInPoster.process_approved_posts() handles reading the file,
        posting to LinkedIn, and moving the file to vault/Done/ itself.
        Therefore this handler must NOT call self._move_to_done() afterward
        (the file lifecycle collision is handled in process_file()).
        """
        from backend.actions.linkedin_poster import LinkedInPoster

        poster = LinkedInPoster(
            vault_path=str(self.vault_path),
            session_path=os.getenv("LINKEDIN_SESSION_PATH", "config/linkedin_session"),
            headless=os.getenv("LINKEDIN_HEADLESS", "true").lower() == "true",
            dry_run=self.config.dry_run,
            dev_mode=self.config.dev_mode,
        )
        try:
            count = await poster.process_approved_posts()
        finally:
            await poster._close_browser()

        if count == 0:
            raise RuntimeError(
                f"LinkedInPoster processed 0 posts for {file_path.name} — "
                "check session state or post content"
            )

    async def _handle_linkedin_reply(self, file_path: Path, _fm: dict[str, Any], _cid: str) -> None:
        """Send an approved LinkedIn message reply via LinkedInReplier.

        LinkedInReplier.process_reply_file() handles reading the file,
        sending the reply on LinkedIn, and moving the file to vault/Done/ itself.
        Therefore this handler must NOT call self._move_to_done() afterward
        (the file lifecycle collision is handled in process_file()).
        """
        from backend.actions.linkedin_replier import LinkedInReplier

        replier = LinkedInReplier(
            vault_path=str(self.vault_path),
            session_path=os.getenv("LINKEDIN_SESSION_PATH", "config/linkedin_session"),
            headless=os.getenv("LINKEDIN_HEADLESS", "true").lower() == "true",
            dry_run=self.config.dry_run,
            dev_mode=self.config.dev_mode,
        )
        try:
            success = await replier.process_reply_file(file_path)
        finally:
            await replier._close_browser()

        if not success:
            raise RuntimeError(
                f"LinkedInReplier failed to send reply for {file_path.name} — "
                "check session state or reply content"
            )

    async def _handle_whatsapp_reply(self, file_path: Path, _fm: dict[str, Any], _cid: str) -> None:
        """Send an approved WhatsApp reply via WhatsAppReplier.

        WhatsAppReplier.process_reply_file() handles reading the file,
        sending the reply on WhatsApp Web, and moving the file to vault/Done/ itself.
        Therefore this handler must NOT call self._move_to_done() afterward.
        """
        from backend.actions.whatsapp_replier import WhatsAppReplier

        replier = WhatsAppReplier(
            vault_path=str(self.vault_path),
            session_path=os.getenv("WHATSAPP_SESSION_PATH", "config/whatsapp_session"),
            headless=os.getenv("WHATSAPP_HEADLESS", "true").lower() == "true",
            dry_run=self.config.dry_run,
            dev_mode=self.config.dev_mode,
        )
        try:
            success = await replier.process_reply_file(file_path)
        finally:
            await replier._close_browser()

        if not success:
            raise RuntimeError(
                f"WhatsAppReplier failed to send reply for {file_path.name} — "
                "check session state or reply content"
            )

    async def _handle_facebook_post(self, file_path: Path, _fm: dict[str, Any], _cid: str) -> None:
        """Publish an approved Facebook post via FacebookPoster.

        FacebookPoster.process_approved_posts() handles reading the file,
        posting to Facebook, and moving the file to vault/Done/ itself.
        Therefore this handler must NOT call self._move_to_done() afterward.
        """
        from backend.actions.facebook_poster import FacebookPoster

        poster = FacebookPoster(
            vault_path=str(self.vault_path),
            session_path=os.getenv("FACEBOOK_SESSION_PATH", "config/meta_session"),
            headless=os.getenv("FACEBOOK_HEADLESS", "true").lower() == "true",
            dry_run=self.config.dry_run,
            dev_mode=self.config.dev_mode,
        )
        try:
            count = await poster.process_approved_posts()
        finally:
            await poster._close_browser()

        if count == 0:
            raise RuntimeError(
                f"FacebookPoster processed 0 posts for {file_path.name} — "
                "check session state or post content"
            )

    async def _handle_instagram_post(self, file_path: Path, _fm: dict[str, Any], _cid: str) -> None:
        """Publish an approved Instagram post via InstagramPoster.

        InstagramPoster.process_approved_posts() handles reading the file,
        posting to Instagram, and moving the file to vault/Done/ itself.
        Therefore this handler must NOT call self._move_to_done() afterward.
        """
        from backend.actions.instagram_poster import InstagramPoster

        poster = InstagramPoster(
            vault_path=str(self.vault_path),
            session_path=os.getenv("INSTAGRAM_SESSION_PATH", "config/meta_session"),
            headless=os.getenv("INSTAGRAM_HEADLESS", "true").lower() == "true",
            dry_run=self.config.dry_run,
            dev_mode=self.config.dev_mode,
        )
        try:
            count = await poster.process_approved_posts()
        finally:
            await poster._close_browser()

        if count == 0:
            raise RuntimeError(
                f"InstagramPoster processed 0 posts for {file_path.name} — "
                "check session state or post content"
            )

    async def _handle_twitter_post(self, file_path: Path, _fm: dict[str, Any], _cid: str) -> None:
        """Publish an approved Twitter post via TwitterPoster.

        TwitterPoster.process_approved_posts() handles reading the file,
        posting to Twitter/X, and moving the file to vault/Done/ itself.
        Therefore this handler must NOT call self._move_to_done() afterward.
        """
        from backend.actions.twitter_poster import TwitterPoster

        poster = TwitterPoster(
            vault_path=str(self.vault_path),
            session_path=os.getenv("TWITTER_SESSION_PATH", "config/twitter_session"),
            headless=os.getenv("TWITTER_HEADLESS", "false").lower() == "true",
            dry_run=self.config.dry_run,
            dev_mode=self.config.dev_mode,
        )
        try:
            count = await poster.process_approved_posts()
        finally:
            await poster._close_browser()

        if count == 0:
            raise RuntimeError(
                f"TwitterPoster processed 0 posts for {file_path.name} — "
                "check session state or post content"
            )

    # ── DEV_MODE Handler ─────────────────────────────────────────

    async def _handle_dev_mode(self, file_path: Path, fm: dict[str, Any], cid: str) -> bool:
        """In DEV_MODE: log the action and move to Done with a note."""
        action_type = fm.get("type", "unknown")
        logger.info("[DEV_MODE] Would execute %s from %s", action_type, file_path.name)

        self._log_event(
            cid, "action_dev_mode", file_path.name, "success", f"[DEV_MODE] type={action_type}"
        )

        # Update frontmatter and move to Done
        try:
            update_frontmatter(
                file_path,
                {
                    "status": "done",
                    "completed_at": now_iso(),
                    "dev_mode_note": "[DEV_MODE] Action logged but not executed",
                },
            )
        except Exception:
            logger.warning("Could not update frontmatter before moving %s", file_path.name)

        self._move_to_done_raw(file_path)
        return True

    # ── Helpers ───────────────────────────────────────────────────

    def _get_gmail_client(self) -> Any:
        """Lazily create the GmailClient."""
        if self._gmail_client is None:
            from backend.mcp_servers.gmail_client import GmailClient

            self._gmail_client = GmailClient(
                credentials_path=os.getenv("GMAIL_CREDENTIALS_PATH", "config/credentials.json"),
                token_path=os.getenv("GMAIL_TOKEN_PATH", "config/token.json"),
            )
        return self._gmail_client

    def _get_rate_limiter(self) -> Any:
        """Lazily create the RateLimiter."""
        if self._rate_limiter is None:
            from backend.mcp_servers.rate_limiter import RateLimiter

            self._rate_limiter = RateLimiter()
        return self._rate_limiter

    def _move_to_done(self, file_path: Path) -> None:
        """Update frontmatter with completion info and move to vault/Done/."""
        try:
            update_frontmatter(file_path, {"status": "done", "completed_at": now_iso()})
        except Exception:
            logger.warning("Could not update frontmatter on %s", file_path.name)
        self._move_to_done_raw(file_path)

    def _move_to_done_raw(self, file_path: Path) -> None:
        """Move file from current location to vault/Done/."""
        import shutil

        self.done_dir.mkdir(parents=True, exist_ok=True)
        dest = self.done_dir / file_path.name
        shutil.move(str(file_path), str(dest))

    @staticmethod
    def _extract_email_body(body_text: str) -> str:
        """Extract email body from markdown content.

        Checks for these section headings in order:
          1. '## Reply Body'   — reply templates created by VaultActionWatcher
          2. '## Email Content' — send templates

        Strips HTML comments (<!-- ... -->) from the extracted text.
        Falls back to the full body only if neither heading is found.
        """
        import re

        lines = body_text.strip().splitlines()

        for heading in ("## reply body", "## email content"):
            in_content = False
            content_lines: list[str] = []

            for line in lines:
                if line.strip().lower().startswith(heading):
                    in_content = True
                    continue
                if in_content and line.strip().startswith("## "):
                    break
                if in_content:
                    content_lines.append(line)

            if content_lines:
                raw = "\n".join(content_lines)
                # Strip HTML comments (e.g. <!-- Write your reply here. -->)
                cleaned = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL).strip()
                if cleaned:
                    return cleaned

        # Fallback: use everything (should rarely happen)
        return body_text.strip()

    def _log_event(
        self, cid: str, action_type: str, target: str, result: str, details: str
    ) -> None:
        """Log an action executor event to the audit trail."""
        try:
            log_action(
                self.log_dir,
                {
                    "timestamp": now_iso(),
                    "correlation_id": cid,
                    "actor": "action_executor",
                    "action_type": action_type,
                    "target": target,
                    "result": result,
                    "parameters": {"details": details, "dev_mode": self.config.dev_mode},
                },
            )
        except Exception:
            logger.exception("Failed to log action executor event")
