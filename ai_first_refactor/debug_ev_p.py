"""
Debug "EV + P" Query - Step-by-Step Analysis
=============================================

This script will:
1. Show what basic_search() finds
2. Show what gets sent to AI as context
3. Capture AI's response
4. Validate against ground truth (should be 11 studies)
"""

import requests
import json
import pandas as pd

# Ground truth check
print("="*80)
print("GROUND TRUTH VALIDATION")
print("="*80)

# Load the actual CSV
df = pd.read_csv("../ESMO_2025_FINAL_20250929.csv")
print(f"Total studies in dataset: {len(df)}")

# Check how many studies actually have both EV and P
# EV = enfortumab vedotin, P = pembrolizumab
if 'search_text_normalized' in df.columns:
    ev_p_mask = (
        df['search_text_normalized'].str.contains('enfortumab', case=False, na=False) &
        df['search_text_normalized'].str.contains('pembrolizumab', case=False, na=False)
    )
    ground_truth_count = ev_p_mask.sum()
    print(f"\nStudies with BOTH 'enfortumab' AND 'pembrolizumab': {ground_truth_count}")

    if ground_truth_count > 0:
        print(f"\nGround Truth Studies:")
        ev_p_studies = df[ev_p_mask][['Identifier', 'Title', 'Speakers']]
        for idx, row in ev_p_studies.iterrows():
            print(f"  [{row['Identifier']}] {row['Title'][:80]}...")
else:
    print("\n[WARNING] search_text_normalized column not found, checking Title only")
    ev_p_mask = (
        df['Title'].str.contains('enfortumab', case=False, na=False) &
        df['Title'].str.contains('pembrolizumab', case=False, na=False)
    )
    ground_truth_count = ev_p_mask.sum()
    print(f"\nStudies with BOTH 'enfortumab' AND 'pembrolizumab' in Title: {ground_truth_count}")

print("\n" + "="*80)
print("TESTING API ENDPOINT")
print("="*80)

# Test the API
url = "http://127.0.0.1:5001/api/chat/ai-first"
payload = {
    "message": "EV + P data updates",
    "drug_filters": [],
    "ta_filters": [],
    "session_filters": [],
    "date_filters": []
}

print(f"\nSending query: '{payload['message']}'")
print(f"Endpoint: {url}\n")

try:
    response = requests.post(url, json=payload, stream=True, timeout=60)

    print(f"Response Status: {response.status_code}\n")

    # Parse SSE stream
    ai_response_text = ""
    table_data = None

    print("Streaming response:")
    print("-" * 80)

    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                data_str = line_str[6:]

                if data_str == '[DONE]':
                    break

                try:
                    event = json.loads(data_str)

                    if 'text' in event:
                        text_chunk = event['text']
                        ai_response_text += text_chunk
                        print(text_chunk, end='', flush=True)

                    if 'table' in event:
                        table_data = event['table']
                        print(f"\n\n[TABLE RECEIVED: {len(table_data)} rows]")

                except json.JSONDecodeError:
                    pass

    print("\n" + "-" * 80)

    # Analysis
    print("\n" + "="*80)
    print("ANALYSIS")
    print("="*80)

    print(f"\nAI Response Length: {len(ai_response_text)} characters")
    print(f"Table Rows Returned: {len(table_data) if table_data else 0}")
    print(f"Ground Truth Count: {ground_truth_count}")

    # Check accuracy
    if table_data:
        returned_count = len(table_data)
        print(f"\nAccuracy Check:")
        print(f"  Expected: {ground_truth_count} studies")
        print(f"  Returned: {returned_count} studies")

        if returned_count == ground_truth_count:
            print(f"  ✓ EXACT MATCH!")
        elif returned_count > ground_truth_count:
            print(f"  ⚠ OVER-INCLUSIVE: {returned_count - ground_truth_count} extra studies")
            print(f"     (May include studies with only EV or only P)")
        else:
            print(f"  ✗ UNDER-INCLUSIVE: Missing {ground_truth_count - returned_count} studies")

        # Show identifiers
        print(f"\n  Returned Study Identifiers:")
        identifiers = [study.get('Identifier', 'N/A') for study in table_data]
        print(f"    {', '.join(identifiers)}")

        # Check AI's understanding
        print(f"\n  Did AI understand abbreviations?")
        ai_lower = ai_response_text.lower()
        if 'enfortumab' in ai_lower:
            print(f"    ✓ AI understood 'EV' = enfortumab vedotin")
        else:
            print(f"    ✗ AI didn't mention 'enfortumab'")

        if 'pembrolizumab' in ai_lower:
            print(f"    ✓ AI understood 'P' = pembrolizumab")
        else:
            print(f"    ✗ AI didn't mention 'pembrolizumab'")

    else:
        print(f"\n✗ NO TABLE RETURNED - Test failed")

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
