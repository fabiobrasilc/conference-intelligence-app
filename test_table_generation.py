#!/usr/bin/env python3
"""
Test table generation functionality specifically
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_table_generation():
    """Test if table generation is working with the avelumab query"""
    print("=== Testing Table Generation ==")

    # Test the avelumab query that should trigger table generation
    test_query = "How many studies or sessions mention avelumab?"

    try:
        response = requests.post(f"{BASE_URL}/api/chat/stream", json={
            'message': test_query
        }, timeout=30, stream=True)

        if response.status_code == 200:
            print(f"[SUCCESS] Chat request successful: {response.status_code}")

            # Track the response type and content
            token_count = 0
            received_table = False
            received_data_table_type = False

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_part = line_str[6:]  # Remove 'data: ' prefix

                        if data_part == '[DONE]':
                            print(f"[SUCCESS] Chat stream completed")
                            break
                        elif 'error' in data_part:
                            print(f"[ERROR] Error in stream: {data_part}")
                        elif data_part.startswith('{"text":'):
                            token_count += 1
                            # Check if this contains table data
                            if 'data_table' in data_part or 'table' in data_part.lower():
                                received_table = True
                                print(f"[SUCCESS] Table-related content found: {data_part[:100]}...")
                        elif 'data_table' in data_part:
                            received_data_table_type = True
                            print(f"[SUCCESS] Data table response type detected: {data_part}")
                        else:
                            # Check for other response indicators
                            if 'data_table' in data_part:
                                print(f"[INFO] Possible table indicator: {data_part[:100]}...")

                # Don't read too much
                if token_count > 200:
                    print(f"[INFO] Stopping after {token_count} tokens")
                    break

            # Summary
            print(f"\n[SUMMARY] Received {token_count} tokens")
            if received_table:
                print("[SUCCESS] Table content detected in response!")
            elif received_data_table_type:
                print("[SUCCESS] Data table response type was detected!")
            else:
                print("[WARNING] No table content detected - may be falling back to narrative")

            return received_table or received_data_table_type

        else:
            print(f"[FAILURE] Chat request failed: {response.status_code}")
            print(f"Error: {response.text[:200]}")
            return False

    except Exception as e:
        print(f"[FAILURE] Test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Table Generation Fix")
    print("=" * 50)

    success = test_table_generation()

    print("\n" + "=" * 50)
    if success:
        print("[SUCCESS] Table generation appears to be working!")
    else:
        print("[FAILURE] Table generation may not be working properly")