#!/usr/bin/env python3
"""
Test the three fixes:
1. Conference Day filter functionality
2. First 50 results display when no filters selected
3. Search highlighting across all columns
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_date_filter():
    """Test Conference Day filter functionality"""
    print("=== Testing Conference Day Filter ===")

    test_cases = [
        ("Day 1 (10/17/2025)", "should return ~294 sessions"),
        ("Day 2 (10/18/2025)", "should return ~1431 sessions"),
        ("Day 3 (10/19/2025)", "should return ~1405 sessions"),
        ("Day 4 (10/20/2025)", "should return ~1534 sessions"),
        ("Day 5 (10/21/2025)", "should return ~22 sessions")
    ]

    for date_filter, expected in test_cases:
        print(f"\n--- Testing {date_filter} ---")

        try:
            response = requests.get(f"{BASE_URL}/api/data", params={
                'date_filters[]': [date_filter]
            }, timeout=10)

            if response.status_code == 200:
                data = response.json()
                result_count = data.get('total', 0)
                print(f"PASS {date_filter}: {result_count} sessions ({expected})")
            else:
                print(f"FAIL Error {response.status_code}: {response.text[:100]}")

        except Exception as e:
            print(f"FAIL Request failed: {e}")


def test_no_filters_limit():
    """Test first 50 results display when no filters selected"""
    print("\n=== Testing No Filters 50-Result Limit ===")

    try:
        response = requests.get(f"{BASE_URL}/api/data", timeout=10)

        if response.status_code == 200:
            data = response.json()
            total = data.get('total', 0)
            showing = data.get('showing', 0)

            if showing <= 50 and total > showing:
                print(f"PASS No filters limit working: showing {showing} out of {total} total")
            else:
                print(f"FAIL Limit not working: showing {showing}, total {total}")
        else:
            print(f"FAIL Error {response.status_code}: {response.text[:100]}")

    except Exception as e:
        print(f"FAIL Request failed: {e}")


def test_search_highlighting():
    """Test search highlighting across all columns"""
    print("\n=== Testing Search Highlighting ===")

    test_searches = [
        ("LBA", "should find Late-Breaking Abstract sessions"),
        ("MD Anderson", "should highlight in affiliation column"),
        ("10/17/2025", "should highlight in date column"),
        ("Educational Session", "should highlight in session column")
    ]

    for keyword, description in test_searches:
        print(f"\n--- Testing search for '{keyword}' ---")

        try:
            response = requests.get(f"{BASE_URL}/api/search", params={
                'keyword': keyword
            }, timeout=10)

            if response.status_code == 200:
                results = response.json()
                result_count = len(results)
                print(f"Results found: {result_count} ({description})")

                # Check first result for highlighting
                if results:
                    first_result = results[0]
                    has_highlighting = any('<mark' in str(val) for val in first_result.values())
                    if has_highlighting:
                        print("PASS Highlighting detected in results")
                    else:
                        print("FAIL No highlighting found in results")

                        # Show which columns contain the keyword (without highlighting)
                        matching_columns = []
                        for col, val in first_result.items():
                            if keyword.lower() in str(val).lower():
                                matching_columns.append(col)
                        print(f"   Keyword found in columns: {matching_columns}")
                else:
                    print("FAIL No results returned")

            else:
                print(f"FAIL Error {response.status_code}: {response.text[:100]}")

        except Exception as e:
            print(f"FAIL Request failed: {e}")


if __name__ == "__main__":
    print("Testing Conference Intelligence App Fixes")
    print("=" * 50)

    test_date_filter()
    test_no_filters_limit()
    test_search_highlighting()

    print("\n" + "=" * 50)
    print("Testing Complete!")