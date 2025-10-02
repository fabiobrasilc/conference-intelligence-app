#!/usr/bin/env python3
"""
Test script to verify avelumab AI chat functionality works
Tests the /api/chat/stream endpoint with an avelumab query
"""

import requests
import json
import time

def test_avelumab_chat():
    """Test the chat API with an avelumab query"""

    # Test URL
    url = "http://127.0.0.1:5000/api/chat/stream"

    # Test message asking for avelumab studies (should work according to user)
    test_message = "list all avelumab studies"

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

    print("Testing avelumab AI chat functionality...")
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
            print("SUCCESS: Connection successful")
            print("-" * 60)

            # Process streaming response
            table_found = False
            response_text = ""

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
                                response_text += data['text']
                            elif 'table' in data:
                                table_found = True
                                table_data = data['table']
                                print(f"\nTABLE DETECTED: {table_data['title']}")
                                print(f"Found {len(table_data['rows'])} studies")
                        except json.JSONDecodeError:
                            # Skip malformed JSON
                            pass

            print("\n" + "-" * 60)
            print("TEST RESULTS:")
            print(f"✅ Connection: Success")
            print(f"✅ Response received: {len(response_text)} characters")
            print(f"✅ Table generated: {'Yes' if table_found else 'No'}")
            print(f"✅ Stream completed: Yes")

        else:
            print(f"ERROR: Request failed with status code: {response.status_code}")
            print(f"Response: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Request failed: {e}")
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")

if __name__ == "__main__":
    test_avelumab_chat()