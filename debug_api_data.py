#!/usr/bin/env python3
"""
Debug the /api/data endpoint directly
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_api_data_endpoint():
    """Test various combinations of the /api/data endpoint"""
    print("=== Debugging /api/data endpoint ===")

    test_cases = [
        ("No filters", {}),
        ("Session filter only", {'session_filters[]': ['Proffered Paper']}),
        ("Drug filter only", {'drug_filters[]': ['All EMD Portfolio']}),
        ("Both filters", {'drug_filters[]': ['All EMD Portfolio'], 'session_filters[]': ['Proffered Paper']})
    ]

    for description, params in test_cases:
        print(f"\n--- {description} ---")
        print(f"Parameters: {params}")

        try:
            response = requests.get(f"{BASE_URL}/api/data", params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                print(f"Status: Success")
                print(f"Response type: {type(data)}")
                print(f"Results count: {len(data)}")

                # Check if this looks like the expected structure
                if isinstance(data, list) and data:
                    first_item = data[0]
                    if isinstance(first_item, dict):
                        print(f"First item keys: {list(first_item.keys())}")
                        if 'Session' in first_item:
                            print(f"First item Session: {first_item.get('Session')}")
                elif isinstance(data, dict):
                    print(f"Dict keys: {list(data.keys())}")

            else:
                print(f"Error: {response.status_code}")
                print(f"Response text: {response.text[:200]}")

        except Exception as e:
            print(f"Request failed: {e}")

if __name__ == "__main__":
    test_api_data_endpoint()