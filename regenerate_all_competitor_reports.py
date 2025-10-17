"""
Regenerate all therapeutic area competitor intelligence reports sequentially.

This script regenerates competitor reports for all 7 TAs with the enhanced
Key Data extraction prompts. Runs sequentially to avoid API rate limits.

Usage:
    python regenerate_all_competitor_reports.py
"""

import subprocess
import time
from datetime import datetime

THERAPEUTIC_AREAS = [
    "Bladder Cancer",
    "Lung Cancer",
    "Colorectal Cancer",
    "Head and Neck Cancer",
    "Renal Cancer",
    "TGCT",
    "Merkel Cell"
]

def regenerate_ta(ta_name: str) -> bool:
    """Regenerate competitor report for one TA."""
    print(f"\n{'='*80}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting: {ta_name}")
    print(f"{'='*80}\n")

    try:
        # Run generation (without --refresh-librarian to use existing librarian cache)
        result = subprocess.run(
            ["python", "generate_deep_intelligence.py", "--button", "competitor", "--ta", ta_name],
            capture_output=False,  # Show output in real-time
            text=True,
            timeout=900  # 15 minute timeout per TA
        )

        if result.returncode == 0:
            print(f"\n✅ [{datetime.now().strftime('%H:%M:%S')}] SUCCESS: {ta_name}")
            return True
        else:
            print(f"\n❌ [{datetime.now().strftime('%H:%M:%S')}] FAILED: {ta_name} (exit code {result.returncode})")
            return False

    except subprocess.TimeoutExpired:
        print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] TIMEOUT: {ta_name} (exceeded 15 minutes)")
        return False
    except Exception as e:
        print(f"\n💥 [{datetime.now().strftime('%H:%M:%S')}] ERROR: {ta_name} - {str(e)}")
        return False

def main():
    """Regenerate all TA competitor reports."""
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                  COMPETITOR REPORT REGENERATION - ALL TAs                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

Starting regeneration for {len(THERAPEUTIC_AREAS)} therapeutic areas...
Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Enhanced prompts include:
- Key Data extraction (Design, Key results, Safety snapshot)
- Flexible structure (skip sections when no data)
- Consistent with Insights report formatting

""")

    start_time = time.time()
    results = {}

    for i, ta in enumerate(THERAPEUTIC_AREAS, 1):
        print(f"\n[Progress: {i}/{len(THERAPEUTIC_AREAS)}]")
        success = regenerate_ta(ta)
        results[ta] = "✅ SUCCESS" if success else "❌ FAILED"

        # Brief pause between TAs to avoid API rate limits
        if i < len(THERAPEUTIC_AREAS):
            print(f"\nWaiting 5 seconds before next TA...")
            time.sleep(5)

    # Summary
    elapsed = time.time() - start_time
    elapsed_min = int(elapsed // 60)
    elapsed_sec = int(elapsed % 60)

    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                              REGENERATION COMPLETE                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

Results Summary:
{'─'*80}
""")

    for ta, result in results.items():
        print(f"  {result:12} {ta}")

    success_count = sum(1 for r in results.values() if "SUCCESS" in r)

    print(f"""
{'─'*80}
Total: {success_count}/{len(THERAPEUTIC_AREAS)} successful
Time: {elapsed_min}m {elapsed_sec}s
End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Updated files:
  - cache/librarian_competitor.json (all TA sections)
  - cache/journalist_competitor.json (all TA reports)

All competitor reports now include detailed Key Data extraction in sections 2.2 and 2.3!
""")

if __name__ == "__main__":
    main()
