#!/usr/bin/env python3
"""
Test the session filtering fix
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_session_filtering():
    """Test session filtering with and without other filters"""
    print("=== Testing Session Filtering Fix ===")

    # Test 1: Proffered Paper alone (should return 276)
    print("\n1. Testing 'Proffered Paper' alone:")
    try:
        response = requests.get(f"{BASE_URL}/api/data", params={
            'drug_filters[]': [],
            'ta_filters[]': [],
            'session_filters[]': ['Proffered Paper']
        }, timeout=10)

        if response.status_code == 200:
            data = response.json()
            print(f"   Results: {len(data)} (should be 276)")
        else:
            print(f"   Error: {response.status_code}")

    except Exception as e:
        print(f"   Failed: {e}")

    # Test 2: Proffered Paper + All EMD Portfolio (should be subset of 276)
    print("\n2. Testing 'Proffered Paper' + 'All EMD Portfolio':")
    try:
        response = requests.get(f"{BASE_URL}/api/data", params={
            'drug_filters[]': ['All EMD Portfolio'],
            'ta_filters[]': [],
            'session_filters[]': ['Proffered Paper']
        }, timeout=10)

        if response.status_code == 200:
            data = response.json()
            print(f"   Results: {len(data)} (should be <= 276, was incorrectly ~76 before)")
        else:
            print(f"   Error: {response.status_code}")

    except Exception as e:
        print(f"   Failed: {e}")

    # Test 3: All session types (should return full dataset)
    print("\n3. Testing no session filters (all sessions):")
    try:
        response = requests.get(f"{BASE_URL}/api/data", params={
            'drug_filters[]': [],
            'ta_filters[]': [],
            'session_filters[]': []
        }, timeout=10)

        if response.status_code == 200:
            data = response.json()
            print(f"   Results: {len(data)} (should be 4686 total, or 50 if limited)")
        else:
            print(f"   Error: {response.status_code}")

    except Exception as e:
        print(f"   Failed: {e}")

if __name__ == "__main__":
    test_session_filtering()