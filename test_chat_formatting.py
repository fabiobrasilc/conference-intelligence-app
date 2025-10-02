#!/usr/bin/env python3
"""
Test script to verify AI chat formatting improvements
Tests the /api/chat/stream endpoint to ensure newlines are properly formatted
"""

import requests
import json
import time

def test_chat_formatting():
    """Test the chat API to ensure proper formatting with newlines"""

    # Test URL
    url = "http://127.0.0.1:5000/api/chat/stream"

    # Test message asking for formatted output
    test_message = "Please explain avelumab's mechanism of action with bullet points and line breaks"

    # Request headers
    headers = {
        'Content-Type': 'application/json'
    }

    # Request payload
    payload = {
        "message": test_message,
        "drug_filters": ["Avelumab Focus"],
        "ta_filters": ["Bladder Cancer"]
    }

    print("Testing AI chat formatting...")
    print(f"URL: {url}")
    print(f"Message: {test_message}")
    print("-" * 60)

    try:
        # Make the request with streaming
        response = requests.post(url,
                               headers=headers,
                               json=payload,
                               stream=True,
                               timeout=60)

        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            print("SUCCESS: Connection successful - streaming response:")
            print("-" * 60)

            # Process streaming response
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]  # Remove 'data: ' prefix
                        if data_str == '[DONE]':
                            print("\nSUCCESS: Stream completed successfully")
                            break

                        try:
                            data = json.loads(data_str)
                            if 'text' in data:
                                # Print each token to show streaming behavior
                                print(data['text'], end='', flush=True)
                        except json.JSONDecodeError:
                            # Skip malformed JSON
                            pass

            print("\n" + "-" * 60)
            print("SUCCESS: Test completed successfully!")
            print("MANUAL VERIFICATION NEEDED:")
            print("   - Check if newlines appear as actual line breaks")
            print("   - Verify bullet points are properly formatted")
            print("   - Confirm text doesn't appear as single paragraph")

        else:
            print(f"ERROR: Request failed with status code: {response.status_code}")
            print(f"Response: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Request failed: {e}")
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")

if __name__ == "__main__":
    test_chat_formatting()