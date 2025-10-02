#!/usr/bin/env python3
"""
Test the search highlighting directly
"""
import requests
import json
from bs4 import BeautifulSoup

BASE_URL = "http://127.0.0.1:5000"

def test_highlighting(keyword):
    """Test search API highlighting with given keyword"""
    print(f"\n=== Testing highlighting for: '{keyword}' ===")

    try:
        response = requests.get(f"{BASE_URL}/api/search", params={
            'keyword': keyword,
            'drug_filters[]': [],
            'ta_filters[]': []
        }, timeout=10)

        if response.status_code == 200:
            data = response.json()
            print(f"Status: Success")
            print(f"Total results: {len(data.get('data', []))}")

            # Look for highlighting in results
            results = data.get('data', [])
            found_highlighting = False

            for i, row in enumerate(results[:3]):
                print(f"\nResult {i+1}:")
                for col in ['Title', 'Speakers', 'Affiliation']:
                    value = row.get(col, '')
                    if '<mark' in str(value):
                        found_highlighting = True
                        print(f"  {col} (with highlighting): {value}")
                        # Extract just the highlighted terms
                        soup = BeautifulSoup(value, 'html.parser')
                        highlighted_terms = [mark.get_text() for mark in soup.find_all('mark')]
                        print(f"    Highlighted terms: {highlighted_terms}")
                    elif str(value).lower() != '' and keyword.lower() in str(value).lower():
                        print(f"  {col} (should be highlighted): {value}")

            if not found_highlighting:
                print("  No highlighting found in results")

        else:
            print(f"Error: {response.status_code}")
            print(f"Response: {response.text}")

    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    print("Testing search highlighting...")

    # Test terms that should highlight properly
    test_highlighting("cancer")
    test_highlighting("MD Anderson")
    test_highlighting("oncology")