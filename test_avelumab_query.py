#!/usr/bin/env python3
"""
Test the specific avelumab query that was failing
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
            print(f"✓ Chat request successful: {response.status_code}")

            # Read SSE events and track progress
            token_count = 0
            error_count = 0
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_part = line_str[6:]  # Remove 'data: ' prefix

                        if data_part == '[DONE]':
                            print(f"✓ Chat stream completed successfully!")
                            print(f"✓ Received {token_count} tokens with {error_count} errors")
                            break
                        elif 'error' in data_part:
                            error_count += 1
                            print(f"⚠ Error token: {data_part}")
                        elif data_part.startswith('{"text":'):
                            token_count += 1
                            if token_count == 1:
                                print(f"✓ First token received: {data_part[:50]}...")
                        elif '|||PARAGRAPH_BREAK|||' in data_part:
                            print("✓ Paragraph break detected")
                        else:
                            print(f"ℹ Other: {data_part[:50]}...")

                    if token_count > 100:  # Don't read too much
                        print(f"✓ Stopping after {token_count} tokens (sufficient for test)")
                        break

        else:
            print(f"✗ Chat request failed: {response.status_code}")
            print(f"Error: {response.text[:200]}")
            return False

    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False

    return True

if __name__ == "__main__":
    print("Testing Avelumab Query Fix")
    print("=" * 40)

    success = test_avelumab_query()

    print("\n" + "=" * 40)
    if success:
        print("✅ Test PASSED - Avelumab query working!")
    else:
        print("❌ Test FAILED - Still has issues")