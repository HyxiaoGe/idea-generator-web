"""
Content moderation audit logging service.
Records all moderation checks for analysis, review, and optimization.
"""
import os
import json
import hashlib
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from queue import Queue


def get_config_value(key: str, default: str = "") -> str:
    """Get configuration value from environment variables."""
    return os.getenv(key, default)


class AuditLogger:
    """
    Audit logger for content moderation events.
    Logs all checks to R2 for analysis and review.
    """

    def __init__(self):
        """Initialize audit logger."""
        self.enabled = get_config_value("AUDIT_LOGGING_ENABLED", "true").lower() in ["true", "1", "yes"]
        self.async_upload = get_config_value("AUDIT_ASYNC_UPLOAD", "true").lower() in ["true", "1", "yes"]

        # R2 storage paths
        self.base_path = "logs/content_moderation"

        # Async upload queue
        self._upload_queue: Queue = Queue()
        self._upload_thread: Optional[threading.Thread] = None

        if self.enabled and self.async_upload:
            self._start_upload_worker()

    def _start_upload_worker(self):
        """Start background thread for async uploads."""
        def worker():
            while True:
                try:
                    log_data = self._upload_queue.get(timeout=5)
                    if log_data is None:  # Shutdown signal
                        break
                    self._upload_to_r2(log_data)
                except Exception as e:
                    # Empty queue or error, continue
                    pass

        self._upload_thread = threading.Thread(target=worker, daemon=True)
        self._upload_thread.start()

    def log_moderation_check(
        self,
        prompt: str,
        layer1_result: Optional[Dict[str, Any]] = None,
        layer2_result: Optional[Dict[str, Any]] = None,
        final_decision: Dict[str, Any] = None,
        context: Optional[Dict[str, Any]] = None
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

            # Upload (async or sync)
            if self.async_upload:
                self._upload_queue.put(log_entry)
            else:
                self._upload_to_r2(log_entry)

        except Exception as e:
            # Don't block user flow on logging errors
            print(f"[AuditLogger] Failed to log: {e}")

    def _build_log_entry(
        self,
        prompt: str,
        layer1_result: Optional[Dict[str, Any]],
        layer2_result: Optional[Dict[str, Any]],
        final_decision: Dict[str, Any],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build structured log entry."""
        import uuid

        timestamp = datetime.now(timezone.utc)
        log_id = str(uuid.uuid4())

        # Hash prompt for deduplication
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()

        # Build log structure
        log_entry = {
            "log_id": log_id,
            "timestamp": timestamp.isoformat(),

            "user_input": {
                "prompt": prompt,
                "prompt_hash": prompt_hash,
                "length": len(prompt)
            },

            "layer1_keyword": layer1_result or {
                "checked": False,
                "passed": None,
                "matched_keywords": [],
                "execution_time_ms": 0,
                "total_keywords_count": 0
            },

            "layer2_ai": layer2_result or {
                "checked": False,
                "passed": None,
                "classification": None,
                "reason": None,
                "ai_raw_response": None,
                "execution_time_ms": 0,
                "model": None,
                "cache_hit": False
            },

            "final_decision": final_decision or {
                "allowed": True,
                "blocked_by": None,
                "blocked_reason": None,
                "total_time_ms": 0
            },

            "context": context or {},

            "analysis_flags": self._generate_analysis_flags(
                prompt, layer1_result, layer2_result, final_decision
            )
        }

        return log_entry

    def _generate_analysis_flags(
        self,
        prompt: str,
        layer1_result: Optional[Dict[str, Any]],
        layer2_result: Optional[Dict[str, Any]],
        final_decision: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate automatic flags for review."""
        flags = {
            "needs_review": False,
            "review_reason": [],
            "confidence": "high"
        }

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

        # Flag 4: Repeated similar prompts (detected via session context)
        # This would require session tracking - placeholder for now

        return flags

    def _upload_to_r2(self, log_entry: Dict[str, Any]):
        """Upload log entry to R2 storage."""
        try:
            from .r2_storage import get_r2_storage

            r2 = get_r2_storage()
            if not r2.is_available:
                return

            # Determine path based on decision
            timestamp = datetime.fromisoformat(log_entry["timestamp"])
            date_str = timestamp.strftime("%Y-%m-%d")
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

            # Build S3 key
            filename = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{log_entry['log_id']}.json"
            key = f"{self.base_path}/{year}/{month}/{day}/{category}/{filename}"

            # Upload to R2
            r2._client.put_object(
                Bucket=r2.bucket_name,
                Key=key,
                Body=json.dumps(log_entry, ensure_ascii=False, indent=2).encode('utf-8'),
                ContentType="application/json",
                Metadata={
                    "log_id": log_entry["log_id"],
                    "allowed": str(allowed).lower(),
                    "needs_review": str(needs_review).lower(),
                    "date": date_str
                }
            )

        except Exception as e:
            print(f"[AuditLogger] Failed to upload to R2: {e}")

    def generate_daily_summary(self, date: str) -> Dict[str, Any]:
        """
        Generate daily summary statistics.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Summary statistics dictionary
        """
        try:
            from .r2_storage import get_r2_storage

            r2 = get_r2_storage()
            if not r2.is_available:
                return {}

            # Parse date
            dt = datetime.strptime(date, "%Y-%m-%d")
            year, month, day = dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")

            # List all logs for the day
            prefix = f"{self.base_path}/{year}/{month}/{day}/"

            response = r2._client.list_objects_v2(
                Bucket=r2.bucket_name,
                Prefix=prefix
            )

            if "Contents" not in response:
                return {"date": date, "total_checks": 0}

            # Download and analyze all logs
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

            for obj in response.get("Contents", []):
                try:
                    # Download log
                    log_response = r2._client.get_object(
                        Bucket=r2.bucket_name,
                        Key=obj["Key"]
                    )
                    log_data = json.loads(log_response["Body"].read().decode("utf-8"))

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
                        # Track keyword frequencies
                        reason = log_data["final_decision"].get("blocked_reason", "")
                        if reason.startswith("keyword:"):
                            keyword = reason.split(":", 1)[1]
                            keyword_counter[keyword] = keyword_counter.get(keyword, 0) + 1

                    elif blocked_by == "ai":
                        layer2_blocks += 1
                        # Track AI categories
                        reason = log_data["final_decision"].get("blocked_reason", "")
                        if reason.startswith("ai:"):
                            category = reason.split(":", 1)[1]
                            ai_category_counter[category] = ai_category_counter.get(category, 0) + 1

                    # Timing stats
                    total_layer1_time += log_data["layer1_keyword"].get("execution_time_ms", 0)
                    total_layer2_time += log_data["layer2_ai"].get("execution_time_ms", 0)

                except Exception as e:
                    print(f"[AuditLogger] Error processing log {obj['Key']}: {e}")
                    continue

            # Build summary
            summary = {
                "date": date,
                "total_checks": total_checks,
                "blocked": blocked_count,
                "allowed": allowed_count,
                "flagged": flagged_count,

                "block_breakdown": {
                    "layer1_keyword": layer1_blocks,
                    "layer2_ai": layer2_blocks
                },

                "top_blocked_keywords": sorted(
                    [{"keyword": k, "count": v} for k, v in keyword_counter.items()],
                    key=lambda x: x["count"],
                    reverse=True
                )[:10],

                "ai_classifications": ai_category_counter,

                "average_times_ms": {
                    "layer1": round(total_layer1_time / total_checks, 2) if total_checks > 0 else 0,
                    "layer2": round(total_layer2_time / total_checks, 2) if total_checks > 0 else 0,
                    "total": round((total_layer1_time + total_layer2_time) / total_checks, 2) if total_checks > 0 else 0
                },

                "accuracy_metrics": {
                    "block_rate": round(blocked_count / total_checks * 100, 2) if total_checks > 0 else 0,
                    "flag_rate": round(flagged_count / total_checks * 100, 2) if total_checks > 0 else 0
                }
            }

            # Save summary to R2
            summary_key = f"{self.base_path}/summary/{date}_summary.json"
            r2._client.put_object(
                Bucket=r2.bucket_name,
                Key=summary_key,
                Body=json.dumps(summary, ensure_ascii=False, indent=2).encode('utf-8'),
                ContentType="application/json"
            )

            return summary

        except Exception as e:
            print(f"[AuditLogger] Failed to generate summary: {e}")
            return {}

    def shutdown(self):
        """Shutdown audit logger and flush queue."""
        if self._upload_thread and self._upload_thread.is_alive():
            self._upload_queue.put(None)  # Shutdown signal
            self._upload_thread.join(timeout=5)


# Global singleton instance
_audit_logger = None


def get_audit_logger() -> AuditLogger:
    """Get or create the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
