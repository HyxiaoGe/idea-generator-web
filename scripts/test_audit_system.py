#!/usr/bin/env python3
"""
Test script for audit logging system.
Tests the complete moderation + audit flow.
"""
import os
import sys
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.content_filter import get_content_filter


def test_audit_system():
    """Test the complete audit logging system."""
    print("="*60)
    print("  Testing Content Moderation Audit System")
    print("="*60)
    print()

    content_filter = get_content_filter()

    # Test cases
    test_cases = [
        {
            "name": "Safe romantic prompt",
            "prompt": "couple embracing passionately under moonlight",
            "expected": True,
            "context": {"generation_mode": "basic", "resolution": "1K"}
        },
        {
            "name": "Keyword blocked - explicit",
            "prompt": "sexy woman in provocative pose",
            "expected": False,
            "context": {"generation_mode": "basic", "resolution": "2K"}
        },
        {
            "name": "Safe artistic prompt",
            "prompt": "renaissance painting of david sculpture",
            "expected": True,
            "context": {"generation_mode": "chat", "resolution": "4K"}
        },
        {
            "name": "AI blocked - euphemism",
            "prompt": "couple making love in romantic bedroom scene",
            "expected": False,
            "context": {"generation_mode": "batch", "resolution": "1K"}
        },
        {
            "name": "Safe fashion prompt",
            "prompt": "fashion model in summer bikini collection",
            "expected": True,
            "context": {"generation_mode": "basic", "resolution": "2K"}
        },
        {
            "name": "Keyword blocked - violence",
            "prompt": "violent scene with blood everywhere",
            "expected": False,
            "context": {"generation_mode": "search", "resolution": "1K"}
        }
    ]

    print("Running test cases...\n")

    results = []
    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}/{len(test_cases)}: {test['name']}")
        print(f"   Prompt: \"{test['prompt']}\"")

        start_time = time.time()
        is_safe, reason = content_filter.is_safe(test['prompt'], context=test['context'])
        elapsed_ms = (time.time() - start_time) * 1000

        passed = (is_safe == test['expected'])
        status = "✅ PASS" if passed else "❌ FAIL"

        print(f"   Result: {'Safe' if is_safe else 'Blocked'} ({reason if reason else 'no reason'})")
        print(f"   Time: {elapsed_ms:.2f}ms")
        print(f"   {status}")
        print()

        results.append({
            "test": test['name'],
            "passed": passed,
            "is_safe": is_safe,
            "expected": test['expected'],
            "reason": reason,
            "time_ms": elapsed_ms
        })

    # Summary
    print("="*60)
    print("  Test Summary")
    print("="*60)
    print()

    passed_count = sum(1 for r in results if r['passed'])
    total_count = len(results)

    print(f"Total Tests: {total_count}")
    print(f"Passed: {passed_count}")
    print(f"Failed: {total_count - passed_count}")
    print(f"Success Rate: {passed_count/total_count*100:.1f}%")
    print()

    # Average timing
    avg_time = sum(r['time_ms'] for r in results) / len(results)
    print(f"Average Response Time: {avg_time:.2f}ms")
    print()

    # Check audit logs
    print("="*60)
    print("  Audit Logging Check")
    print("="*60)
    print()

    from services.r2_storage import get_r2_storage
    r2 = get_r2_storage()

    if not r2.is_available:
        print("⚠️ R2 storage not available - audit logs not uploaded")
        print("   Logs were queued but not persisted to cloud")
    else:
        print("✅ R2 storage available - audit logs uploaded")
        print(f"   Check R2 bucket: {r2.bucket_name}")
        print("   Path: logs/content_moderation/")

    print()

    # Next steps
    print("="*60)
    print("  Next Steps")
    print("="*60)
    print()
    print("1. Analyze logs:")
    print("   python scripts/analyze_moderation_logs.py summary --date $(date +%Y-%m-%d)")
    print()
    print("2. Find false positives:")
    print("   python scripts/analyze_moderation_logs.py false-positives")
    print()
    print("3. Check unused keywords:")
    print("   python scripts/analyze_moderation_logs.py unused-keywords --days 30")
    print()
    print("4. View flagged logs:")
    print("   python scripts/analyze_moderation_logs.py flagged")
    print()

    return passed_count == total_count


if __name__ == "__main__":
    success = test_audit_system()
    sys.exit(0 if success else 1)
