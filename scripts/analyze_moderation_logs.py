#!/usr/bin/env python3
"""
Content moderation log analysis tool.
Analyzes audit logs to identify patterns, false positives, and optimization opportunities.
"""
import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Any

# Add parent directory to path to import services
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.audit_logger import get_audit_logger
from services.r2_storage import get_r2_storage


class ModerationLogAnalyzer:
    """Analyzer for content moderation audit logs."""

    def __init__(self):
        """Initialize analyzer."""
        self.audit_logger = get_audit_logger()
        self.r2 = get_r2_storage()

        if not self.r2.is_available:
            print("⚠️ R2 storage not available. Cannot analyze logs.")
            sys.exit(1)

    def generate_daily_summary(self, date: str):
        """
        Generate and display daily summary.

        Args:
            date: Date in YYYY-MM-DD format
        """
        print(f"\n{'='*60}")
        print(f"  Content Moderation Summary - {date}")
        print(f"{'='*60}\n")

        summary = self.audit_logger.generate_daily_summary(date)

        if not summary or summary.get("total_checks", 0) == 0:
            print("No moderation checks found for this date.\n")
            return

        # Overall stats
        print(f"📊 Overall Statistics")
        print(f"   Total Checks:    {summary['total_checks']}")
        print(f"   ✅ Allowed:      {summary['allowed']} ({summary['allowed']/summary['total_checks']*100:.1f}%)")
        print(f"   ❌ Blocked:      {summary['blocked']} ({summary['blocked']/summary['total_checks']*100:.1f}%)")
        print(f"   🚩 Flagged:      {summary['flagged']} ({summary['flagged']/summary['total_checks']*100:.1f}%)")
        print()

        # Block breakdown
        print(f"🛡️ Block Breakdown")
        print(f"   Layer 1 (Keywords): {summary['block_breakdown']['layer1_keyword']}")
        print(f"   Layer 2 (AI):       {summary['block_breakdown']['layer2_ai']}")
        print()

        # Top blocked keywords
        if summary['top_blocked_keywords']:
            print(f"🔑 Top Blocked Keywords")
            for item in summary['top_blocked_keywords'][:5]:
                print(f"   • {item['keyword']:<20} ({item['count']} times)")
            print()

        # AI classifications
        if summary['ai_classifications']:
            print(f"🤖 AI Classifications")
            for category, count in summary['ai_classifications'].items():
                print(f"   • {category:<20} ({count} times)")
            print()

        # Performance metrics
        print(f"⚡ Performance Metrics")
        print(f"   Layer 1 Avg:  {summary['average_times_ms']['layer1']:.2f}ms")
        print(f"   Layer 2 Avg:  {summary['average_times_ms']['layer2']:.2f}ms")
        print(f"   Total Avg:    {summary['average_times_ms']['total']:.2f}ms")
        print()

        # Accuracy
        print(f"📈 Accuracy Metrics")
        print(f"   Block Rate:  {summary['accuracy_metrics']['block_rate']:.2f}%")
        print(f"   Flag Rate:   {summary['accuracy_metrics']['flag_rate']:.2f}%")
        print()

    def find_false_positive_candidates(self, date: str, limit: int = 20) -> List[Dict]:
        """
        Find potential false positives - blocked prompts that might be legitimate.

        Criteria:
        - Long prompts (>100 chars) blocked by single keyword
        - Prompts with common words that might be false matches
        - Prompts flagged for review

        Args:
            date: Date in YYYY-MM-DD format
            limit: Maximum results to return

        Returns:
            List of candidate log entries
        """
        print(f"\n🔍 Analyzing False Positive Candidates for {date}...\n")

        dt = datetime.strptime(date, "%Y-%m-%d")
        year, month, day = dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")

        # Get blocked logs
        prefix = f"{self.audit_logger.base_path}/{year}/{month}/{day}/blocked/"

        candidates = []

        try:
            response = self.r2._client.list_objects_v2(
                Bucket=self.r2.bucket_name,
                Prefix=prefix
            )

            for obj in response.get("Contents", []):
                # Download log
                log_response = self.r2._client.get_object(
                    Bucket=self.r2.bucket_name,
                    Key=obj["Key"]
                )
                log_data = json.loads(log_response["Body"].read().decode("utf-8"))

                # Criteria for false positive candidate
                prompt = log_data["user_input"]["prompt"]
                prompt_len = log_data["user_input"]["length"]
                blocked_by = log_data["final_decision"]["blocked_by"]
                needs_review = log_data["analysis_flags"]["needs_review"]

                # Long prompts blocked by keywords might be false positives
                if blocked_by == "keyword" and prompt_len > 100:
                    candidates.append({
                        "log_id": log_data["log_id"],
                        "prompt": prompt[:200] + "..." if len(prompt) > 200 else prompt,
                        "reason": log_data["final_decision"]["blocked_reason"],
                        "length": prompt_len,
                        "needs_review": needs_review,
                        "score": 0.7  # High probability
                    })

                # Flagged for review
                elif needs_review:
                    candidates.append({
                        "log_id": log_data["log_id"],
                        "prompt": prompt[:200] + "..." if len(prompt) > 200 else prompt,
                        "reason": log_data["final_decision"]["blocked_reason"],
                        "length": prompt_len,
                        "needs_review": True,
                        "score": 0.6  # Medium probability
                    })

        except Exception as e:
            print(f"Error analyzing logs: {e}")
            return []

        # Sort by score and limit
        candidates.sort(key=lambda x: x["score"], reverse=True)
        candidates = candidates[:limit]

        # Display results
        if not candidates:
            print("✅ No false positive candidates found.\n")
        else:
            print(f"Found {len(candidates)} potential false positives:\n")
            for i, candidate in enumerate(candidates, 1):
                print(f"{i}. Prompt: {candidate['prompt']}")
                print(f"   Reason: {candidate['reason']}")
                print(f"   Length: {candidate['length']} chars")
                print(f"   Score:  {candidate['score']:.2f}")
                print()

        return candidates

    def find_unused_keywords(self, days: int = 30) -> List[str]:
        """
        Find keywords that haven't been triggered in N days.
        These might be candidates for removal.

        Args:
            days: Number of days to analyze

        Returns:
            List of unused keywords
        """
        print(f"\n🔎 Finding keywords unused in the last {days} days...\n")

        # Load current keywords
        from services.content_filter import get_content_filter
        content_filter = get_content_filter()
        all_keywords = set(content_filter.banned_keywords)

        triggered_keywords = set()

        # Analyze logs for the past N days
        today = datetime.now()
        for i in range(days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            dt = datetime.strptime(date, "%Y-%m-%d")
            year, month, day = dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")

            prefix = f"{self.audit_logger.base_path}/{year}/{month}/{day}/blocked/"

            try:
                response = self.r2._client.list_objects_v2(
                    Bucket=self.r2.bucket_name,
                    Prefix=prefix
                )

                for obj in response.get("Contents", []):
                    log_response = self.r2._client.get_object(
                        Bucket=self.r2.bucket_name,
                        Key=obj["Key"]
                    )
                    log_data = json.loads(log_response["Body"].read().decode("utf-8"))

                    blocked_reason = log_data["final_decision"].get("blocked_reason", "")
                    if blocked_reason.startswith("keyword:"):
                        keyword = blocked_reason.split(":", 1)[1]
                        triggered_keywords.add(keyword)

            except Exception:
                # Date might not exist, skip
                continue

        # Find unused
        unused = sorted(all_keywords - triggered_keywords)

        print(f"📊 Keyword Usage Statistics:")
        print(f"   Total Keywords:     {len(all_keywords)}")
        print(f"   Used (last {days}d):    {len(triggered_keywords)}")
        print(f"   Unused:             {len(unused)}")
        print()

        if unused and len(unused) <= 20:
            print(f"Unused keywords:")
            for keyword in unused:
                print(f"   • {keyword}")
            print()

        return unused

    def view_flagged_logs(self, date: str, limit: int = 10):
        """
        View logs flagged for manual review.

        Args:
            date: Date in YYYY-MM-DD format
            limit: Maximum results to display
        """
        print(f"\n🚩 Flagged Logs for Review - {date}\n")

        dt = datetime.strptime(date, "%Y-%m-%d")
        year, month, day = dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")

        prefix = f"{self.audit_logger.base_path}/{year}/{month}/{day}/flagged/"

        try:
            response = self.r2._client.list_objects_v2(
                Bucket=self.r2.bucket_name,
                Prefix=prefix
            )

            if "Contents" not in response:
                print("✅ No flagged logs found for this date.\n")
                return

            count = 0
            for obj in response.get("Contents", []):
                if count >= limit:
                    break

                log_response = self.r2._client.get_object(
                    Bucket=self.r2.bucket_name,
                    Key=obj["Key"]
                )
                log_data = json.loads(log_response["Body"].read().decode("utf-8"))

                count += 1

                print(f"{count}. Log ID: {log_data['log_id']}")
                print(f"   Timestamp: {log_data['timestamp']}")
                print(f"   Prompt: {log_data['user_input']['prompt'][:150]}...")
                print(f"   Decision: {'Blocked' if not log_data['final_decision']['allowed'] else 'Allowed'}")
                print(f"   Reason: {log_data['final_decision'].get('blocked_reason', 'N/A')}")
                print(f"   Review Reason: {', '.join(log_data['analysis_flags']['review_reason'])}")
                print(f"   Confidence: {log_data['analysis_flags']['confidence']}")
                print()

        except Exception as e:
            print(f"Error viewing flagged logs: {e}\n")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze content moderation logs")

    parser.add_argument(
        "command",
        choices=["summary", "false-positives", "unused-keywords", "flagged"],
        help="Analysis command to run"
    )

    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Date to analyze (YYYY-MM-DD, default: today)"
    )

    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to analyze (for unused-keywords)"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results to show"
    )

    args = parser.parse_args()

    analyzer = ModerationLogAnalyzer()

    if args.command == "summary":
        analyzer.generate_daily_summary(args.date)

    elif args.command == "false-positives":
        analyzer.find_false_positive_candidates(args.date, args.limit)

    elif args.command == "unused-keywords":
        analyzer.find_unused_keywords(args.days)

    elif args.command == "flagged":
        analyzer.view_flagged_logs(args.date, args.limit)


if __name__ == "__main__":
    main()
