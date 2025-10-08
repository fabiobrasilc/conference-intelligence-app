"""
Quick test script for AI-first functionality
Run this to test the AI pipeline independently
"""

import pandas as pd
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add ai_first_refactor to path
ai_first_path = Path(__file__).parent / 'ai_first_refactor'
sys.path.insert(0, str(ai_first_path))

from ai_assistant import handle_chat_query

# Load data
print("Loading CSV...")
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv')
print(f"Loaded {len(df)} studies\n")

# Add search_text_normalized column if needed
if 'search_text_normalized' not in df.columns:
    print("Adding search_text_normalized column...")
    df['search_text'] = df.apply(lambda x: ' | '.join([
        str(x.get('Title', '')),
        str(x.get('Session', '')),
        str(x.get('Theme', '')),
        str(x.get('Speakers', '')),
        str(x.get('Affiliation', '')),
        str(x.get('Speaker Location', '')),
        str(x.get('Room', '')),
        str(x.get('Date', '')),
        str(x.get('Time', ''))
    ]), axis=1)
    df['search_text_normalized'] = df['search_text'].str.lower()

# Filter to bladder cancer (simulating UI filter)
print("Filtering to Bladder Cancer...")
bladder_df = df[df['Theme'].str.contains('GU tumours, renal & urothelial', case=False, na=False)]
print(f"Filtered to {len(bladder_df)} bladder cancer studies\n")

# Test 1: Casual query
print("="*70)
print("TEST 1: Casual query 'Hello!'")
print("="*70)
result = handle_chat_query(
    df=bladder_df,
    user_query="Hello!",
    active_filters={'ta': ['Bladder Cancer'], 'drug': [], 'session': [], 'date': []}
)

print(f"\nFiltered data size: {len(result['filtered_data'])}")
print("AI Response:")
for token in result['response_stream']:
    print(token, end='', flush=True)
print("\n")

# Test 2: Data query
print("\n" + "="*70)
print("TEST 2: Data query 'EV + P studies'")
print("="*70)
result = handle_chat_query(
    df=bladder_df,
    user_query="EV + P studies",
    active_filters={'ta': ['Bladder Cancer'], 'drug': [], 'session': [], 'date': []}
)

print(f"\nFiltered data size: {len(result['filtered_data'])}")
if not result['filtered_data'].empty:
    print("Sample IDs:", result['filtered_data']['Identifier'].head(5).tolist())
print("\nAI Response:")
for token in result['response_stream']:
    print(token, end='', flush=True)
print("\n")

print("\n" + "="*70)
print("Tests complete!")
print("="*70)
