#!/usr/bin/env python3
"""
Direct test of MD Anderson query to compare with avelumab behavior
"""

import requests
import json

def test_query(query_text, label):
    """Test a query and show the result"""
    url = "http://127.0.0.1:5000/api/chat/stream"

    payload = {
        "message": query_text,
        "drug_filters": [],
        "ta_filters": []
    }

    print(f"\n{'='*60}")
    print(f"Testing: {label}")
    print(f"Query: '{query_text}'")
    print('='*60)

    try:
        response = requests.post(url, headers={'Content-Type': 'application/json'},
                               json=payload, stream=True, timeout=30)

        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            has_table = False
            has_ai_text = False
            ai_tokens = []

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')

                    if line_str.startswith('event: table'):
                        has_table = True
                        print("TABLE DETECTED")

                    elif line_str.startswith('data: '):
                        data_str = line_str[6:]

                        if data_str == '[DONE]':
                            break

                        try:
                            data = json.loads(data_str)
                            if 'text' in data:
                                has_ai_text = True
                                ai_tokens.append(data['text'])
                        except json.JSONDecodeError:
                            pass

            print(f"Table Generated: {has_table}")
            print(f"AI Text Streamed: {has_ai_text}")
            if has_ai_text:
                ai_response = ''.join(ai_tokens)
                print(f"AI Response Length: {len(ai_response)} characters")
                print(f"AI Response Preview: {ai_response[:100]}...")
            else:
                print("NO AI TEXT RECEIVED")

        else:
            print(f"ERROR: {response.status_code}")

    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    # Test avelumab (working)
    test_query("list all avelumab studies", "AVELUMAB (Working)")

    # Test MD Anderson (not working)
    test_query("How many studies from MD Anderson?", "MD ANDERSON (Problem)")