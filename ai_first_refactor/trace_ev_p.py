"""
Trace EV + P Query Through the System
======================================

This simulates what the AI-first endpoint does, showing each step.
"""

import sys
from pathlib import Path
import pandas as pd

# Add parent directory to path to import ai_assistant
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Import functions
from improved_search import precompute_search_text

# Add ai_first_refactor to path
sys.path.insert(0, str(Path(__file__).parent))
from ai_assistant import basic_search, prepare_ai_context

print("="*80)
print("TRACING 'EV + P' QUERY THROUGH AI-FIRST SYSTEM")
print("="*80)

# Step 1: Load data (simulating what app.py does)
print("\n[STEP 1] Loading conference data...")
df = pd.read_csv(parent_dir / "ESMO_2025_FINAL_20250929.csv")
print(f"  Loaded: {len(df)} studies")

# Precompute search text
df = precompute_search_text(df)
print(f"  Precomputed search_text_normalized column")

# Step 2: Simulate user query
user_query = "EV + P data updates"
print(f"\n[STEP 2] User Query: '{user_query}'")

# Step 3: Run basic_search
print(f"\n[STEP 3] Running basic_search()...")
filtered_df = basic_search(df, user_query)
print(f"  Input: {len(df)} studies")
print(f"  Output: {len(filtered_df)} studies")

if len(filtered_df) < 50:
    print(f"\n  Filtered Studies:")
    for idx, row in filtered_df.iterrows():
        print(f"    [{row['Identifier']}] {row['Title'][:70]}...")

# Step 4: Check ground truth
print(f"\n[STEP 4] Ground Truth Validation...")
# Check for studies with BOTH enfortumab AND pembrolizumab
ev_p_mask = (
    df['search_text_normalized'].str.contains('enfortumab', case=False, na=False) &
    df['search_text_normalized'].str.contains('pembrolizumab', case=False, na=False)
)
ground_truth_df = df[ev_p_mask]
print(f"  Studies with BOTH 'enfortumab' AND 'pembrolizumab': {len(ground_truth_df)}")

print(f"\n  Ground Truth Identifiers:")
print(f"    {', '.join(ground_truth_df['Identifier'].tolist())}")

# Step 5: Prepare AI context
print(f"\n[STEP 5] Preparing AI context...")
active_filters = {'drug': [], 'ta': [], 'session': [], 'date': []}
ai_messages = prepare_ai_context(user_query, filtered_df, active_filters)

print(f"  Number of messages: {len(ai_messages)}")
print(f"  System prompt length: {len(ai_messages[0]['content'])} chars")
print(f"  User message length: {len(ai_messages[1]['content'])} chars")

# Calculate approximate tokens (rough estimate: 1 token ~ 4 chars)
total_chars = sum(len(msg['content']) for msg in ai_messages)
est_tokens = total_chars // 4
print(f"  Estimated tokens: ~{est_tokens:,}")

# Step 6: Show what JSON data AI receives
print(f"\n[STEP 6] Dataset sent to AI...")
import json
user_msg = ai_messages[1]['content']

# Extract the JSON part
if "**STUDIES DATA:**" in user_msg:
    json_start = user_msg.index("**STUDIES DATA:**") + len("**STUDIES DATA:**")
    json_str = user_msg[json_start:].strip()

    # Find where user query instructions start
    if "Please answer" in json_str:
        json_end = json_str.index("Please answer")
        json_str = json_str[:json_end].strip()

    try:
        studies_data = json.loads(json_str)
        print(f"  Number of studies in JSON: {len(studies_data)}")
        print(f"\n  First 3 study identifiers in AI context:")
        for i, study in enumerate(studies_data[:3]):
            print(f"    {i+1}. {study.get('Identifier', 'N/A')}: {study.get('Title', '')[:60]}...")

        # Check if ground truth studies are in AI context
        ai_identifiers = {study.get('Identifier') for study in studies_data}
        gt_identifiers = set(ground_truth_df['Identifier'].tolist())

        print(f"\n  Ground Truth Coverage Check:")
        print(f"    Ground truth studies: {len(gt_identifiers)}")
        print(f"    Present in AI context: {len(ai_identifiers & gt_identifiers)}")
        print(f"    Missing from AI context: {len(gt_identifiers - ai_identifiers)}")

        if gt_identifiers - ai_identifiers:
            print(f"\n    Missing identifiers: {', '.join(sorted(gt_identifiers - ai_identifiers))}")

    except Exception as e:
        print(f"  Error parsing JSON: {e}")

# Step 7: Analysis
print(f"\n" + "="*80)
print("ANALYSIS")
print("="*80)

print(f"\n1. basic_search() returned {len(filtered_df)} studies")
print(f"2. Ground truth is {len(ground_truth_df)} studies")
print(f"3. Difference: {abs(len(filtered_df) - len(ground_truth_df))} studies")

if len(filtered_df) > len(ground_truth_df):
    print(f"   → basic_search() is OVER-INCLUSIVE (includes extra studies)")
    print(f"   → This is OK - AI should filter down from the {len(filtered_df)} studies")
elif len(filtered_df) < len(ground_truth_df):
    print(f"   → basic_search() is UNDER-INCLUSIVE (missing relevant studies)")
    print(f"   → This is BAD - AI can't find studies it wasn't given!")
else:
    print(f"   → basic_search() returned exact count!")

# Check why basic_search might have returned wrong count
print(f"\n4. Why did basic_search() return {len(filtered_df)} studies?")
print(f"   Query: '{user_query}'")
print(f"   Search terms extracted from 'EV + P data updates':")

stop_words = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'show', 'me', 'tell', 'about', 'what', 'are', 'is', 'give', 'all',
    'sessions', 'studies', 'presentations', 'data', 'can', 'you', 'please'
}
words = user_query.lower().split()
search_terms = [w for w in words if w not in stop_words and len(w) > 2]
print(f"   → {search_terms}")
print(f"   → Searches for any study containing: {'|'.join(search_terms)}")
print(f"   → Problem: 'updates' is generic, 'ev' and 'p' are very short")

print(f"\n5. The AI's challenge:")
print(f"   - AI receives {len(filtered_df)} studies in context")
print(f"   - Must understand 'EV' = enfortumab vedotin, 'P' = pembrolizumab")
print(f"   - Must find the {len(ground_truth_df)} that have BOTH drugs")
print(f"   - AI said: 'no specific studies directly mentioning EV+P'")
print(f"   - This is WRONG - there ARE {len(ground_truth_df)} EV+P combination studies!")

print(f"\n" + "="*80)
