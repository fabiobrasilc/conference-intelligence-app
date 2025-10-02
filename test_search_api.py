#!/usr/bin/env python3
"""
Test the search API to verify our fixes
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_search(keyword):
    """Test search API with given keyword"""
    print(f"\n=== Testing search for: '{keyword}' ===")

    try:
        response = requests.get(f"{BASE_URL}/api/search", params={
            'keyword': keyword,
            'drug_filters[]': [],  # No drug filters
            'ta_filters[]': []     # No TA filters
        })

        if response.status_code == 200:
            data = response.json()
            print(f"Status: Success")
            print(f"Total results: {len(data.get('data', []))}")

            # Show first few results to check highlighting
            results = data.get('data', [])
            for i, row in enumerate(results[:3]):
                print(f"\nResult {i+1}:")
                print(f"  Title: {row.get('Title', 'N/A')}")
                print(f"  Speakers: {row.get('Speakers', 'N/A')}")
                print(f"  Affiliation: {row.get('Affiliation', 'N/A')}")

        else:
            print(f"Error: {response.status_code}")
            print(f"Response: {response.text}")

    except requests.RequestException as e:
        print(f"Request failed: {e}")

# Test the searches that were problematic
if __name__ == "__main__":
    print("Testing search API fixes...")

    # Test MD Anderson (should find exactly 3)
    test_search("MD Anderson")

    # Test LBA (should find actual LBA identifiers, not "St Albans")
    test_search("LBA")

    # Test a simple word that should get highlighted properly
    test_search("cancer")