"""
Content moderation audit logging service.
Records all moderation checks for analysis, review, and optimization.

Logs are written to local filesystem under outputs/logs/content_moderation/.
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from queue import Queue
from typing import Any

logger = logging.getLogger(__name__)


def get_config_value(key: str, default: str = "") -> str:
    """Get configuration value from environment variables."""
    return os.getenv(key, default)


class AuditLogger:
    """
    Audit logger for content moderation events.
    Logs all checks to local filesystem for analysis and review.
    """

    def __init__(self):
        """Initialize audit logger."""
        self.enabled = get_config_value("AUDIT_LOGGING_ENABLED", "true").lower() in [
            "true",
            "1",
            "yes",
        ]
        self.async_write = get_config_value("AUDIT_ASYNC_UPLOAD", "true").lower() in [
            "true",
            "1",
            "yes",
        ]

        # Local storage base path
        self.base_path = Path("outputs/logs/content_moderation")

        # Async write queue
        self._write_queue: Queue = Queue()
        self._write_thread: threading.Thread | None = None

        if self.enabled and self.async_write:
            self._start_write_worker()

    def _start_write_worker(self):
        """Start background thread for async writes."""

        def worker():
            while True:
                try:
                    log_data = self._write_queue.get(timeout=5)
                    if log_data is None:  # Shutdown signal
                        break
                    self._write_to_local(log_data)
                    self._write_to_db(log_data)
                except Exception:
                    # Empty queue or error, continue
                    pass

        self._write_thread = threading.Thread(target=worker, daemon=True)
        self._write_thread.start()

    def log_moderation_check(
        self,
        prompt: str,
        layer1_result: dict[str, Any] | None = None,
        layer2_result: dict[str, Any] | None = None,
        final_decision: dict[str, Any] = None,
        context: dict[str, Any] | None = None,
    ):
        """
        Log a content moderation check.

        Args:
            prompt: User's input prompt
            layer1_result: Keyword filter results
            layer2_result: AI moderation results
            final_decision: Final allow/block decision
            context: Additional context (mode, user, session, etc.)
        """
        if not self.enabled:
            return

        try:
            # Generate log entry
            log_entry = self._build_log_entry(
                prompt, layer1_result, layer2_result, final_decision, context
            )

            # Write (async or sync)
            if self.async_write:
                self._write_queue.put(log_entry)
            else:
                self._write_to_local(log_entry)
                self._write_to_db(log_entry)

        except Exception as e:
            # Don't block user flow on logging errors
            print(f"[AuditLogger] Failed to log: {e}")

    def _build_log_entry(
        self,
        prompt: str,
        layer1_result: dict[str, Any] | None,
        layer2_result: dict[str, Any] | None,
        final_decision: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build structured log entry."""
        import uuid

        timestamp = datetime.now(UTC)
        log_id = str(uuid.uuid4())

        # Hash prompt for deduplication
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()

        # Build log structure
        log_entry = {
            "log_id": log_id,
            "timestamp": timestamp.isoformat(),
            "user_input": {"prompt": prompt, "prompt_hash": prompt_hash, "length": len(prompt)},
            "layer1_keyword": layer1_result
            or {
                "checked": False,
                "passed": None,
                "matched_keywords": [],
                "execution_time_ms": 0,
                "total_keywords_count": 0,
            },
            "layer2_ai": layer2_result
            or {
                "checked": False,
                "passed": None,
                "classification": None,
                "reason": None,
                "ai_raw_response": None,
                "execution_time_ms": 0,
                "model": None,
                "cache_hit": False,
            },
            "final_decision": final_decision
            or {"allowed": True, "blocked_by": None, "blocked_reason": None, "total_time_ms": 0},
            "context": context or {},
            "analysis_flags": self._generate_analysis_flags(
                prompt, layer1_result, layer2_result, final_decision
            ),
        }

        return log_entry

    def _generate_analysis_flags(
        self,
        prompt: str,
        layer1_result: dict[str, Any] | None,
        layer2_result: dict[str, Any] | None,
        final_decision: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate automatic flags for review."""
        flags = {"needs_review": False, "review_reason": [], "confidence": "high"}

        # Flag 1: Contradictory results
        if layer1_result and layer2_result:
            if layer1_result.get("passed") != layer2_result.get("passed"):
                flags["needs_review"] = True
                flags["review_reason"].append("contradictory_layers")
                flags["confidence"] = "low"

        # Flag 2: AI error or timeout
        if layer2_result and layer2_result.get("checked"):
            if layer2_result.get("execution_time_ms", 0) > 3000:
                flags["needs_review"] = True
                flags["review_reason"].append("ai_slow_response")

            if "error" in str(layer2_result.get("reason", "")).lower():
                flags["needs_review"] = True
                flags["review_reason"].append("ai_error")

        # Flag 3: Edge case - long prompt blocked by single keyword
        if not final_decision.get("allowed"):
            if len(prompt) > 100 and final_decision.get("blocked_by") == "keyword":
                # Long descriptive prompts might have false positives
                flags["needs_review"] = True
                flags["review_reason"].append("long_prompt_keyword_block")
                flags["confidence"] = "medium"

        return flags

    def _write_to_local(self, log_entry: dict[str, Any]):
        """Write log entry to local filesystem."""
        try:
            # Determine path based on decision
            timestamp = datetime.fromisoformat(log_entry["timestamp"])
            year = timestamp.strftime("%Y")
            month = timestamp.strftime("%m")
            day = timestamp.strftime("%d")

            allowed = log_entry["final_decision"]["allowed"]
            needs_review = log_entry["analysis_flags"]["needs_review"]

            # Categorize into folders
            if needs_review:
                category = "flagged"
            elif allowed:
                category = "allowed"
            else:
                category = "blocked"

            # Build local path
            filename = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{log_entry['log_id']}.json"
            log_dir = self.base_path / year / month / day / category
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / filename

            # Write to file
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(log_entry, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"[AuditLogger] Failed to write log: {e}")

    def _write_to_db(self, log_entry: dict[str, Any]):
        """Write queryable summary to PostgreSQL via AuditRepository."""
        try:
            from database import is_database_available

            if not is_database_available():
                return

            # Map log entry to DB columns
            final_decision = log_entry.get("final_decision", {})
            allowed = final_decision.get("allowed", True)
            needs_review = log_entry.get("analysis_flags", {}).get("needs_review", False)

            if needs_review:
                filter_result = "flagged"
            elif allowed:
                filter_result = "allowed"
            else:
                filter_result = "blocked"

            prompt = log_entry.get("user_input", {}).get("prompt", "")
            blocked_reason = final_decision.get("blocked_reason")

            async def _persist():
                from database import get_session
                from database.repositories import AuditRepository

                async for session in get_session():
                    repo = AuditRepository(session)
                    await repo.create_audit_log(
                        action="content_moderation",
                        prompt=prompt,
                        filter_result=filter_result,
                        blocked_reason=blocked_reason,
                    )
                    break

            # Run async DB write from sync context
            try:
                loop = asyncio.get_running_loop()
                # Already in an async context — schedule as a task
                loop.create_task(_persist())
            except RuntimeError:
                # No running loop (background thread) — create one
                asyncio.run(_persist())

        except Exception as e:
            logger.warning(f"Failed to write audit log to database: {e}")

    def generate_daily_summary(self, date: str) -> dict[str, Any]:
        """
        Generate daily summary statistics.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Summary statistics dictionary
        """
        try:
            # Parse date
            dt = datetime.strptime(date, "%Y-%m-%d")
            year, month, day = dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")

            # List all logs for the day
            day_dir = self.base_path / year / month / day

            if not day_dir.exists():
                return {"date": date, "total_checks": 0}

            # Read and analyze all log files
            total_checks = 0
            blocked_count = 0
            allowed_count = 0
            flagged_count = 0

            layer1_blocks = 0
            layer2_blocks = 0

            keyword_counter = {}
            ai_category_counter = {}

            total_layer1_time = 0
            total_layer2_time = 0

            for category_dir in day_dir.iterdir():
                if not category_dir.is_dir():
                    continue
                for log_file in category_dir.glob("*.json"):
                    try:
                        with open(log_file, encoding="utf-8") as f:
                            log_data = json.load(f)

                        total_checks += 1

                        # Count decisions
                        if log_data["final_decision"]["allowed"]:
                            allowed_count += 1
                        else:
                            blocked_count += 1

                        if log_data["analysis_flags"]["needs_review"]:
                            flagged_count += 1

                        # Count block reasons
                        blocked_by = log_data["final_decision"].get("blocked_by")
                        if blocked_by == "keyword":
                            layer1_blocks += 1
                            reason = log_data["final_decision"].get("blocked_reason", "")
                            if reason.startswith("keyword:"):
                                keyword = reason.split(":", 1)[1]
                                keyword_counter[keyword] = keyword_counter.get(keyword, 0) + 1

                        elif blocked_by == "ai":
                            layer2_blocks += 1
                            reason = log_data["final_decision"].get("blocked_reason", "")
                            if reason.startswith("ai:"):
                                category = reason.split(":", 1)[1]
                                ai_category_counter[category] = (
                                    ai_category_counter.get(category, 0) + 1
                                )

                        # Timing stats
                        total_layer1_time += log_data["layer1_keyword"].get("execution_time_ms", 0)
                        total_layer2_time += log_data["layer2_ai"].get("execution_time_ms", 0)

                    except Exception as e:
                        print(f"[AuditLogger] Error processing log {log_file}: {e}")
                        continue

            # Build summary
            summary = {
                "date": date,
                "total_checks": total_checks,
                "blocked": blocked_count,
                "allowed": allowed_count,
                "flagged": flagged_count,
                "block_breakdown": {"layer1_keyword": layer1_blocks, "layer2_ai": layer2_blocks},
                "top_blocked_keywords": sorted(
                    [{"keyword": k, "count": v} for k, v in keyword_counter.items()],
                    key=lambda x: x["count"],
                    reverse=True,
                )[:10],
                "ai_classifications": ai_category_counter,
                "average_times_ms": {
                    "layer1": round(total_layer1_time / total_checks, 2) if total_checks > 0 else 0,
                    "layer2": round(total_layer2_time / total_checks, 2) if total_checks > 0 else 0,
                    "total": round((total_layer1_time + total_layer2_time) / total_checks, 2)
                    if total_checks > 0
                    else 0,
                },
                "accuracy_metrics": {
                    "block_rate": round(blocked_count / total_checks * 100, 2)
                    if total_checks > 0
                    else 0,
                    "flag_rate": round(flagged_count / total_checks * 100, 2)
                    if total_checks > 0
                    else 0,
                },
            }

            # Save summary locally
            summary_dir = self.base_path / "summary"
            summary_dir.mkdir(parents=True, exist_ok=True)
            summary_file = summary_dir / f"{date}_summary.json"
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

            return summary

        except Exception as e:
            print(f"[AuditLogger] Failed to generate summary: {e}")
            return {}

    def shutdown(self):
        """Shutdown audit logger and flush queue."""
        if self._write_thread and self._write_thread.is_alive():
            self._write_queue.put(None)  # Shutdown signal
            self._write_thread.join(timeout=5)


# Global singleton instance
_audit_logger = None


def get_audit_logger() -> AuditLogger:
    """Get or create the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
