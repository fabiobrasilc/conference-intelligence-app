#!/usr/bin/env python3
"""
Debug script to test AI chat functionality directly
Tests the /api/chat/stream endpoint to diagnose the issue
"""

import requests
import json
import time

def test_chat_debug():
    """Test the chat API to diagnose why it's not working"""

    # Test URL
    url = "http://127.0.0.1:5000/api/chat/stream"

    # Simple test message
    test_message = "How many studies from MD Anderson?"

    # Request headers
    headers = {
        'Content-Type': 'application/json'
    }

    # Request payload
    payload = {
        "message": test_message,
        "drug_filters": [],
        "ta_filters": []
    }

    print("Testing AI chat endpoint...")
    print(f"URL: {url}")
    print(f"Message: {test_message}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print("-" * 60)

    try:
        # Make the request with streaming
        print("Making POST request...")
        response = requests.post(url,
                               headers=headers,
                               json=payload,
                               stream=True,
                               timeout=30)

        print(f"Status Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")

        if response.status_code == 200:
            print("SUCCESS: Connection established")
            print("-" * 60)
            print("Streaming response:")

            # Process streaming response
            for i, line in enumerate(response.iter_lines()):
                if line:
                    line_str = line.decode('utf-8')
                    print(f"Line {i}: {line_str}")

                    if line_str.startswith('data: '):
                        data_str = line_str[6:]  # Remove 'data: ' prefix
                        if data_str == '[DONE]':
                            print("Stream completed")
                            break

                        try:
                            data = json.loads(data_str)
                            print(f"Parsed data: {data}")
                        except json.JSONDecodeError as e:
                            print(f"JSON decode error: {e}")

                # Stop after 50 lines to avoid spam
                if i > 50:
                    print("Stopping after 50 lines...")
                    break

        else:
            print(f"ERROR: Request failed with status code: {response.status_code}")
            print(f"Response text: {response.text}")

    except requests.exceptions.Timeout:
        print("ERROR: Request timed out")
    except requests.exceptions.ConnectionError as e:
        print(f"ERROR: Connection error: {e}")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Request failed: {e}")
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")

if __name__ == "__main__":
    test_chat_debug()