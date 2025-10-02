#!/usr/bin/env python3
"""
Simple test to see what the search API returns
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

try:
    response = requests.get(f"{BASE_URL}/api/search", params={
        'keyword': 'cancer',
        'drug_filters[]': [],
        'ta_filters[]': []
    }, timeout=10)

    print(f"Status Code: {response.status_code}")
    print(f"Content-Type: {response.headers.get('content-type', 'unknown')}")

    if response.status_code == 200:
        try:
            data = response.json()
            print(f"Response type: {type(data)}")

            if isinstance(data, dict):
                print(f"Keys: {list(data.keys())}")
                if 'data' in data:
                    print(f"Data length: {len(data['data'])}")
                    if data['data']:
                        print(f"First item type: {type(data['data'][0])}")
                        if isinstance(data['data'][0], dict):
                            print(f"First item keys: {list(data['data'][0].keys())}")
                            # Check for highlighting in title
                            if 'Title' in data['data'][0]:
                                title = data['data'][0]['Title']
                                print(f"Sample title: {title}")
                                if '<mark' in str(title):
                                    print("  -> Contains highlighting!")
                                else:
                                    print("  -> No highlighting found")
            elif isinstance(data, list):
                print(f"List length: {len(data)}")
                if data:
                    print(f"First item: {data[0]}")

        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Raw response: {response.text[:500]}")
    else:
        print(f"Error response: {response.text}")

except Exception as e:
    print(f"Request failed: {e}")

print("\n" + "="*50)
print("Also testing a simple raw request...")

try:
    response = requests.get(f"{BASE_URL}/api/data", timeout=10)
    print(f"Data API Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Data API returns {len(data)} items")
except Exception as e:
    print(f"Data API failed: {e}")