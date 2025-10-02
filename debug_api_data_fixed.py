#!/usr/bin/env python3
"""
Debug the /api/data endpoint - fixed version
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_api_data_endpoint_fixed():
    """Test various combinations of the /api/data endpoint - checking data array"""
    print("=== Debugging /api/data endpoint (Fixed) ===")

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
                result = response.json()
                print(f"Status: Success")

                if isinstance(result, dict):
                    # Check the actual data array
                    data_array = result.get('data', [])
                    total = result.get('total', 0)
                    showing = result.get('showing', 0)

                    print(f"Data array length: {len(data_array)}")
                    print(f"Total results: {total}")
                    print(f"Showing: {showing}")

                    # Check first item session type
                    if data_array and isinstance(data_array[0], dict):
                        first_item = data_array[0]
                        if 'Session' in first_item:
                            print(f"First item Session: {first_item.get('Session')}")

            else:
                print(f"Error: {response.status_code}")
                print(f"Response text: {response.text[:200]}")

        except Exception as e:
            print(f"Request failed: {e}")

if __name__ == "__main__":
    test_api_data_endpoint_fixed()