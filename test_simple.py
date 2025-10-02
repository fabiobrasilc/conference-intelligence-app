#!/usr/bin/env python3
"""
Simple test without Unicode characters
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_avelumab_query():
    """Test the specific query that was causing issues"""
    print("=== Testing Avelumab Query ===")

    # The exact query that was failing
    test_query = "How many studies or sessions mention avelumab?"

    try:
        # Send chat request via POST SSE streaming
        response = requests.post(f"{BASE_URL}/api/chat/stream", json={
            'message': test_query
        }, timeout=30, stream=True)

        if response.status_code == 200:
            print(f"PASS: Chat request successful: {response.status_code}")

            # Read SSE events and track progress
            token_count = 0
            error_count = 0
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_part = line_str[6:]  # Remove 'data: ' prefix

                        if data_part == '[DONE]':
                            print(f"PASS: Chat stream completed successfully!")
                            print(f"PASS: Received {token_count} tokens with {error_count} errors")
                            return True
                        elif 'error' in data_part:
                            error_count += 1
                            print(f"ERROR: {data_part}")
                        elif data_part.startswith('{"text":'):
                            token_count += 1
                            if token_count == 1:
                                print(f"PASS: First token received")
                        else:
                            pass  # Other messages

                    if token_count > 50:  # Don't read too much
                        print(f"PASS: Stopping after {token_count} tokens (sufficient for test)")
                        return True

        else:
            print(f"FAIL: Chat request failed: {response.status_code}")
            print(f"Error: {response.text[:200]}")
            return False

    except Exception as e:
        print(f"FAIL: Test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Avelumab Query Fix")
    print("=" * 40)

    success = test_avelumab_query()

    print("\n" + "=" * 40)
    if success:
        print("SUCCESS: Test PASSED - Avelumab query working!")
    else:
        print("FAILURE: Test FAILED - Still has issues")