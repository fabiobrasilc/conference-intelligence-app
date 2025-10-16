"""
Test Case: Nivolumab in Renal Cancer on 10/18
==============================================

User Query: "I am curious about the studies being presented on 10/18 about nivolumab in renal cancer."

Expected Result: 6 studies (user manually verified)

Expected AI Extraction:
- dates: ["10/18"]
- drugs: ["nivolumab"]
- therapeutic_areas: ["renal cancer", "renal cell carcinoma", "kidney cancer"]
"""

import sys
import pandas as pd
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / '.env')

sys.path.insert(0, str(Path(__file__).parent.parent))

from improved_search import precompute_search_text
from ai_assistant import handle_chat_query

# Load data
print("Loading conference data...")
df = pd.read_csv("../ESMO_2025_FINAL_20250929.csv")
df = precompute_search_text(df)
print(f"Loaded: {len(df)} studies\n")

# Ground truth - manual verification
print("=" * 80)
print("GROUND TRUTH (Manual Verification)")
print("=" * 80)

# Filter for 10/18 + nivolumab + renal
date_mask = df['Date'].str.contains('10/18', case=False, na=False)
nivo_mask = df['search_text_normalized'].str.contains('nivolumab', case=False, na=False)
renal_mask = (
    df['search_text_normalized'].str.contains('renal', case=False, na=False) |
    df['search_text_normalized'].str.contains('kidney', case=False, na=False) |
    df['search_text_normalized'].str.contains('RCC', case=False, na=False)
)

ground_truth = df[date_mask & nivo_mask & renal_mask]
ground_truth_ids = sorted(ground_truth['Identifier'].dropna().tolist())

print(f"\nGround truth: {len(ground_truth)} studies")
print(f"Identifiers: {', '.join(map(str, ground_truth_ids))}")

if len(ground_truth) > 0:
    print("\nSample titles:")
    for idx, row in ground_truth.head(3).iterrows():
        print(f"  - {row['Identifier']}: {row['Title'][:80]}...")

# Run two-step AI flow
print("\n" + "=" * 80)
print("RUNNING TWO-STEP AI FLOW")
print("=" * 80)

result = handle_chat_query(
    df=df,
    user_query="I am curious about the studies being presented on 10/18 about nivolumab in renal cancer.",
    active_filters={}
)

filtered_df = result['filtered_data']
returned_ids = sorted(filtered_df['Identifier'].dropna().tolist())

print("\n" + "=" * 80)
print("VALIDATION RESULTS")
print("=" * 80)

count_match = len(filtered_df) == len(ground_truth)
print(f"\nCount Check: {'PASS' if count_match else 'FAIL'}")
print(f"  Expected: {len(ground_truth)} studies")
print(f"  Got: {len(filtered_df)} studies")

if len(filtered_df) > 0:
    print(f"\nReturned Identifiers: {', '.join(map(str, returned_ids))}")

    # Check if IDs match
    ids_match = set(returned_ids) == set(ground_truth_ids)
    print(f"\nIdentifier Match: {'PASS' if ids_match else 'PARTIAL'}")

    if not ids_match:
        missing = set(ground_truth_ids) - set(returned_ids)
        extra = set(returned_ids) - set(ground_truth_ids)
        if missing:
            print(f"  Missing IDs: {', '.join(map(str, missing))}")
        if extra:
            print(f"  Extra IDs: {', '.join(map(str, extra))}")

print("\n" + "=" * 80)
print(f"OVERALL: {'PASS - AI flow working correctly!' if count_match else 'FAIL - Count mismatch'}")
print("=" * 80)

# Show AI response
print("\n" + "=" * 80)
print("AI RESPONSE")
print("=" * 80)
print()

for token in result['response_stream']:
    # Handle unicode gracefully
    try:
        print(token, end='', flush=True)
    except UnicodeEncodeError:
        print(token.encode('ascii', 'ignore').decode('ascii'), end='', flush=True)

print("\n")
