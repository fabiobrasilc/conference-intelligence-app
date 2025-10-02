#!/usr/bin/env python3
"""
Test multi-filtering functionality - when users select multiple filters
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_multi_filtering():
    """Test various combinations of multiple filters"""
    print("=== Testing Multi-Filter Functionality ===")

    test_cases = [
        {
            "name": "Multiple Drug Filters",
            "params": {
                'drug_filters[]': ['Avelumab Focus', 'Tepotinib Focus']
            },
            "expected": "Should return sessions for both Avelumab AND Tepotinib"
        },
        {
            "name": "Multiple TA Filters",
            "params": {
                'ta_filters[]': ['Bladder Cancer', 'Lung Cancer']
            },
            "expected": "Should return sessions for both Bladder AND Lung cancer"
        },
        {
            "name": "Multiple Session Filters",
            "params": {
                'session_filters[]': ['Proffered Paper', 'Mini Oral Session']
            },
            "expected": "Should return both Proffered Papers AND Mini Oral sessions"
        },
        {
            "name": "Multiple Date Filters",
            "params": {
                'date_filters[]': ['Day 1 (10/17/2025)', 'Day 2 (10/18/2025)']
            },
            "expected": "Should return sessions from both Day 1 AND Day 2"
        },
        {
            "name": "Drug + TA Combination",
            "params": {
                'drug_filters[]': ['Avelumab Focus'],
                'ta_filters[]': ['Bladder Cancer']
            },
            "expected": "Should return Avelumab sessions in Bladder Cancer"
        },
        {
            "name": "Complex Multi-Filter",
            "params": {
                'drug_filters[]': ['Avelumab Focus', 'All EMD Portfolio'],
                'ta_filters[]': ['Bladder Cancer', 'Renal Cancer'],
                'session_filters[]': ['Proffered Paper'],
                'date_filters[]': ['Day 3 (10/19/2025)', 'Day 4 (10/20/2025)']
            },
            "expected": "Should combine all selected filters with OR logic"
        }
    ]

    for test_case in test_cases:
        print(f"\n--- {test_case['name']} ---")
        print(f"Testing: {test_case['params']}")
        print(f"Expected: {test_case['expected']}")

        try:
            response = requests.get(f"{BASE_URL}/api/data", params=test_case['params'], timeout=10)

            if response.status_code == 200:
                data = response.json()
                total = data.get('total', 0)
                showing = data.get('showing', 0)

                print(f"PASS: {total} total results, showing {showing}")

                # Check if we got reasonable results (not zero, not all 4686)
                if total > 0 and total < 4686:
                    print(f"✓ Filtering appears to be working correctly")
                elif total == 0:
                    print(f"⚠ No results - might indicate too restrictive filtering or issue")
                elif total == 4686:
                    print(f"⚠ All results returned - might indicate filters not being applied")

                # Show filter context if available
                filter_context = data.get('filter_context', {})
                if filter_context:
                    print(f"Filter summary: {filter_context.get('filter_summary', 'N/A')}")

            else:
                print(f"FAIL Error {response.status_code}: {response.text[:100]}")

        except Exception as e:
            print(f"FAIL Request failed: {e}")

def test_single_vs_multi_comparison():
    """Compare single filter vs multi-filter results to verify OR logic"""
    print("\n=== Testing Single vs Multi-Filter Logic ===")

    # Test: Avelumab alone vs Tepotinib alone vs Both together
    print("\n--- Drug Filter OR Logic Test ---")

    filters_to_test = [
        (['Avelumab Focus'], "Avelumab only"),
        (['Tepotinib Focus'], "Tepotinib only"),
        (['Avelumab Focus', 'Tepotinib Focus'], "Avelumab OR Tepotinib")
    ]

    results = []

    for filters, description in filters_to_test:
        try:
            response = requests.get(f"{BASE_URL}/api/data", params={
                'drug_filters[]': filters
            }, timeout=10)

            if response.status_code == 200:
                data = response.json()
                total = data.get('total', 0)
                results.append((description, total))
                print(f"{description}: {total} results")
            else:
                results.append((description, f"Error {response.status_code}"))
                print(f"{description}: Error {response.status_code}")

        except Exception as e:
            results.append((description, f"Failed: {e}"))
            print(f"{description}: Failed: {e}")

    # Verify OR logic: Combined should be >= individual results
    if len(results) == 3 and all(isinstance(r[1], int) for r in results):
        avelumab_count = results[0][1]
        tepotinib_count = results[1][1]
        combined_count = results[2][1]

        print(f"\n--- Logic Verification ---")
        print(f"Avelumab: {avelumab_count}")
        print(f"Tepotinib: {tepotinib_count}")
        print(f"Combined: {combined_count}")

        # Combined should be at least as many as the larger individual filter
        max_individual = max(avelumab_count, tepotinib_count)
        if combined_count >= max_individual:
            print(f"✅ OR logic working: Combined ({combined_count}) >= Max individual ({max_individual})")
        else:
            print(f"❌ OR logic issue: Combined ({combined_count}) < Max individual ({max_individual})")

if __name__ == "__main__":
    print("Testing Multi-Filter Functionality")
    print("=" * 50)

    test_multi_filtering()
    test_single_vs_multi_comparison()

    print("\n" + "=" * 50)
    print("Multi-Filter Testing Complete!")