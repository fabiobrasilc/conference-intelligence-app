#!/usr/bin/env python3
"""
Detailed test for table generation functionality
"""
import requests
import json
import time

BASE_URL = "http://127.0.0.1:5000"

def test_specific_table_query():
    """Test specific queries that should trigger table generation"""
    print("=== Testing Specific Table Generation Query ===")

    # These queries should definitely trigger data_table response type
    test_queries = [
        "list all avelumab studies",
        "show me avelumab research",
        "how many avelumab sessions are there",
        "give me a table of avelumab studies"
    ]

    for query in test_queries:
        print(f"\n[TEST] Query: '{query}'")

        try:
            response = requests.post(f"{BASE_URL}/api/chat/stream", json={
                'message': query
            }, timeout=30, stream=True)

            if response.status_code == 200:
                print(f"[SUCCESS] Request successful: {response.status_code}")

                token_count = 0
                found_table_content = False
                found_data_table_type = False
                first_tokens = []

                for line in response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            data_part = line_str[6:]  # Remove 'data: ' prefix

                            if data_part == '[DONE]':
                                print(f"[INFO] Stream completed with {token_count} tokens")
                                break
                            elif 'error' in data_part:
                                print(f"[ERROR] Error: {data_part}")
                            elif data_part.startswith('{"text":'):
                                token_count += 1
                                if token_count <= 5:  # Capture first few tokens
                                    first_tokens.append(data_part)

                                # Check for table indicators
                                if any(word in data_part.lower() for word in ['table', 'study', 'title', 'speaker', 'avelumab']):
                                    found_table_content = True
                                    print(f"[FOUND] Table-related content in token {token_count}: {data_part[:100]}...")
                            elif 'data_table' in data_part:
                                found_data_table_type = True
                                print(f"[FOUND] Data table response type: {data_part}")

                        # Don't read too much
                        if token_count > 50:
                            print(f"[INFO] Stopping after {token_count} tokens")
                            break

                # Results for this query
                print(f"[RESULT] Tokens received: {token_count}")
                print(f"[RESULT] Table content found: {found_table_content}")
                print(f"[RESULT] Data table type detected: {found_data_table_type}")
                if first_tokens:
                    print(f"[RESULT] First token: {first_tokens[0][:100]}...")

                if found_table_content or found_data_table_type:
                    print(f"[SUCCESS] Query '{query}' appears to be generating table content")
                    return True
                else:
                    print(f"[WARNING] Query '{query}' may not be generating table content")

            else:
                print(f"[FAILURE] Request failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"[FAILURE] Test failed: {e}")
            return False

        time.sleep(1)  # Brief pause between tests

    return False

if __name__ == "__main__":
    print("Testing Detailed Table Generation")
    print("=" * 60)

    success = test_specific_table_query()

    print("\n" + "=" * 60)
    if success:
        print("[SUCCESS] Table generation appears to be working!")
    else:
        print("[INVESTIGATION NEEDED] Table generation needs further debugging")