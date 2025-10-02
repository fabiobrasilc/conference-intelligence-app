#!/usr/bin/env python3
"""
Test avelumab search to see the highlighting issue
"""
import requests
import json
from bs4 import BeautifulSoup

BASE_URL = "http://127.0.0.1:5000"

def test_avelumab_highlighting():
    """Test avelumab search highlighting"""
    print("=== Testing avelumab highlighting ===")

    try:
        response = requests.get(f"{BASE_URL}/api/search", params={
            'keyword': 'avelumab',
            'drug_filters[]': [],
            'ta_filters[]': []
        }, timeout=10)

        if response.status_code == 200:
            data = response.json()
            print(f"Found {len(data)} results for 'avelumab'")

            # Check first few results for highlighting patterns
            for i, row in enumerate(data[:5]):
                print(f"\n--- Result {i+1} ---")
                for col in ['Title', 'Speakers', 'Affiliation']:
                    value = row.get(col, '')
                    if '<mark' in str(value):
                        print(f"{col}: {value}")
                        # Extract highlighted terms
                        soup = BeautifulSoup(value, 'html.parser')
                        highlighted_terms = [mark.get_text() for mark in soup.find_all('mark')]
                        print(f"  Highlighted: {highlighted_terms}")

        else:
            print(f"Error: {response.status_code}")

    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_avelumab_highlighting()

    print("\n" + "="*50)

    # Also test a non-drug term
    print("=== Testing non-drug term 'bladder' ===")

    try:
        response = requests.get(f"{BASE_URL}/api/search", params={
            'keyword': 'bladder',
            'drug_filters[]': [],
            'ta_filters[]': []
        }, timeout=10)

        if response.status_code == 200:
            data = response.json()
            print(f"Found {len(data)} results for 'bladder'")

            # Check first result
            if data:
                row = data[0]
                for col in ['Title', 'Speakers', 'Affiliation']:
                    value = row.get(col, '')
                    if '<mark' in str(value):
                        print(f"{col}: {value}")

    except Exception as e:
        print(f"Bladder search failed: {e}")