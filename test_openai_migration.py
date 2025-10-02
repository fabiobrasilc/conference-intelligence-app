#!/usr/bin/env python3
"""
Test the OpenAI API migration by trying a simple chat request
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_chat_functionality():
    """Test if chat functionality works with new API"""
    print("=== Testing AI Chat Functionality ===")

    # Test a simple query
    test_query = "What are the key findings about avelumab?"

    try:
        # Send chat request via POST SSE streaming
        response = requests.post(f"{BASE_URL}/api/chat/stream", json={
            'message': test_query
        }, timeout=30, stream=True)

        if response.status_code == 200:
            print(f"Chat request successful: {response.status_code}")

            # Read first few SSE events
            lines_read = 0
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_part = line_str[6:]  # Remove 'data: ' prefix
                        if data_part == '[DONE]':
                            print("Chat stream completed successfully!")
                            break
                        elif data_part.startswith('{"text":'):
                            # This is a token, chat is working!
                            print("✓ AI chat tokens are streaming correctly")
                            break
                        else:
                            print(f"Received: {data_part}")

                    lines_read += 1
                    if lines_read > 10:  # Don't read too much
                        break

        else:
            print(f"Chat request failed: {response.status_code}")
            print(f"Error: {response.text[:200]}")

    except Exception as e:
        print(f"Chat test failed: {e}")

def test_intelligence_button():
    """Test if KOL intelligence button works"""
    print("\n=== Testing KOL Intelligence Button ===")

    try:
        response = requests.get(f"{BASE_URL}/api/playbook/kol/stream", params={
            'drug_filters[]': ['Avelumab Focus']
        }, timeout=30, stream=True)

        if response.status_code == 200:
            print(f"KOL button request successful: {response.status_code}")

            lines_read = 0
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if 'token' in line_str:
                        print("✓ KOL analysis tokens are streaming correctly")
                        break
                    elif 'error' in line_str:
                        print(f"✗ Error in KOL stream: {line_str}")
                        break

                lines_read += 1
                if lines_read > 10:
                    break

        else:
            print(f"KOL button request failed: {response.status_code}")
            print(f"Error: {response.text[:200]}")

    except Exception as e:
        print(f"KOL test failed: {e}")

if __name__ == "__main__":
    print("Testing OpenAI API Migration")
    print("=" * 40)

    test_chat_functionality()
    test_intelligence_button()

    print("\n" + "=" * 40)
    print("API Migration Test Complete!")