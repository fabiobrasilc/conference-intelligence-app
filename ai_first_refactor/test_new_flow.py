"""
Test the new two-step AI flow with EV + P query
"""

import sys
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# Add paths
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))
sys.path.insert(0, str(Path(__file__).parent))

from improved_search import precompute_search_text
from ai_assistant import handle_chat_query

print("="*80)
print("TESTING NEW TWO-STEP AI FLOW")
print("="*80)

# Load data
print("\nLoading conference data...")
df = pd.read_csv(parent_dir / "ESMO_2025_FINAL_20250929.csv")
df = precompute_search_text(df)
print(f"Loaded: {len(df)} studies")

# Ground truth check
ev_p_mask = (
    df['search_text_normalized'].str.contains('enfortumab', case=False, na=False) &
    df['search_text_normalized'].str.contains('pembrolizumab', case=False, na=False)
)
ground_truth = df[ev_p_mask]
print(f"Ground truth: {len(ground_truth)} EV+P combination studies")
print(f"Identifiers: {', '.join(ground_truth['Identifier'].tolist())}")

# Test the new flow
print("\n" + "="*80)
print("RUNNING TWO-STEP FLOW")
print("="*80)

user_query = "EV + P"
active_filters = {'drug': [], 'ta': [], 'session': [], 'date': []}

result = handle_chat_query(df, user_query, active_filters)

print("\n" + "="*80)
print("RESULTS")
print("="*80)

filtered_data = result['filtered_data']
print(f"\nFiltered studies returned: {len(filtered_data)}")
print(f"Ground truth: {len(ground_truth)}")

if len(filtered_data) > 0:
    print(f"\nReturned identifiers:")
    print(f"  {', '.join(filtered_data['Identifier'].dropna().tolist())}")

print(f"\nAI Response:")
print("-" * 80)
for token in result['response_stream']:
    print(token, end='', flush=True)
print("\n" + "-" * 80)

# Accuracy check
if len(filtered_data) == len(ground_truth):
    print(f"\n✓ PERFECT MATCH: {len(filtered_data)} studies (expected {len(ground_truth)})")
else:
    print(f"\n⚠ COUNT MISMATCH: Got {len(filtered_data)}, expected {len(ground_truth)}")

print("\n" + "="*80)
