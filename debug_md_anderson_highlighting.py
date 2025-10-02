#!/usr/bin/env python3
"""
Debug why MD Anderson highlighting is not working
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def debug_md_anderson():
    print("=== Debugging MD Anderson Search Highlighting ===")

    try:
        response = requests.get(f"{BASE_URL}/api/search", params={
            'keyword': 'MD Anderson'
        }, timeout=10)

        if response.status_code == 200:
            results = response.json()
            print(f"Total results: {len(results)}")

            if results:
                # Check first few results
                for i, result in enumerate(results[:3]):
                    print(f"\n--- Result {i+1} ---")
                    for col, val in result.items():
                        if 'MD Anderson' in str(val).upper():
                            contains_mark = '<mark' in str(val)
                            print(f"{col}: {str(val)[:100]}... (has highlighting: {contains_mark})")

                # Test the highlighting pattern manually
                print("\n--- Manual Pattern Testing ---")
                import re
                keyword = "MD Anderson"
                pattern = re.compile(f'({re.escape(keyword)})', re.IGNORECASE)
                test_text = "The University of Texas MD Anderson Cancer Center"
                highlighted = pattern.sub(r'<mark>\1</mark>', test_text)
                print(f"Original: {test_text}")
                print(f"Highlighted: {highlighted}")
                print(f"Should work: {'<mark>' in highlighted}")

        else:
            print(f"Error {response.status_code}: {response.text[:200]}")

    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    debug_md_anderson()