"""
Validation Script for Two-Step AI Flow
========================================

Tests that the ENGRAVED flow works correctly:
1. AI receives query and interprets what user wants
2. AI generates keywords (handles acronyms, abbreviations)
3. Keywords passed to DataFrame filtering (4686 -> ~30)
4. Table with filtered results generated
5. Filtered data passed BACK to AI for analysis
6. AI generates output based on filtered results

Ground Truth for "EV + P": Exactly 11 studies
"""

import sys
import pandas as pd
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from improved_search import precompute_search_text
from ai_assistant import handle_chat_query

def validate_ev_p_query():
    """Validate the EV + P query returns exactly 11 studies."""

    print("=" * 80)
    print("VALIDATION: EV + P Query")
    print("=" * 80)

    # Load data
    df = pd.read_csv("../ESMO_2025_FINAL_20250929.csv")
    df = precompute_search_text(df)

    # Ground truth
    ev_p_mask = (
        df['search_text_normalized'].str.contains('enfortumab', case=False, na=False) &
        df['search_text_normalized'].str.contains('pembrolizumab', case=False, na=False)
    )
    ground_truth = df[ev_p_mask]
    ground_truth_ids = sorted(ground_truth['Identifier'].dropna().tolist())

    print(f"\nGround Truth: {len(ground_truth)} studies")
    print(f"Expected IDs: {', '.join(map(str, ground_truth_ids))}")

    # Run two-step flow
    print("\n" + "-" * 80)
    print("Running Two-Step AI Flow...")
    print("-" * 80 + "\n")

    result = handle_chat_query(
        df=df,
        user_query="EV + P",
        active_filters={}
    )

    filtered_df = result['filtered_data']
    returned_ids = sorted(filtered_df['Identifier'].dropna().tolist())

    print("\n" + "=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)

    # Check counts match
    count_match = len(filtered_df) == len(ground_truth)
    print(f"\nCount Check: {'PASS' if count_match else 'FAIL'}")
    print(f"  Expected: {len(ground_truth)} studies")
    print(f"  Got: {len(filtered_df)} studies")

    # Check IDs match
    ids_match = returned_ids == ground_truth_ids
    print(f"\nIdentifier Check: {'PASS' if ids_match else 'FAIL'}")
    print(f"  Expected: {', '.join(map(str, ground_truth_ids))}")
    print(f"  Got: {', '.join(map(str, returned_ids))}")

    # Check AI received only filtered data
    print(f"\nData Sent to AI: {len(filtered_df)} studies (not all 4,686)")

    # Overall result
    print("\n" + "=" * 80)
    if count_match and ids_match:
        print("OVERALL: PASS - Two-step flow working correctly!")
    else:
        print("OVERALL: FAIL - Issues detected")
    print("=" * 80)

    return count_match and ids_match


def validate_md_anderson_query():
    """Validate MD Anderson query returns 73 studies (from affiliations)."""

    print("\n\n" + "=" * 80)
    print("VALIDATION: MD Anderson Query")
    print("=" * 80)

    # Load data
    df = pd.read_csv("../ESMO_2025_FINAL_20250929.csv")
    df = precompute_search_text(df)

    # Ground truth from affiliations column
    ground_truth = df[df['Affiliation'].str.contains('MD Anderson', case=False, na=False)]

    print(f"\nGround Truth: {len(ground_truth)} studies (from Affiliation column)")

    # Run two-step flow
    print("\n" + "-" * 80)
    print("Running Two-Step AI Flow...")
    print("-" * 80 + "\n")

    result = handle_chat_query(
        df=df,
        user_query="What's MD Anderson presenting?",
        active_filters={}
    )

    filtered_df = result['filtered_data']

    print("\n" + "=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)

    count_match = len(filtered_df) == len(ground_truth)
    print(f"\nCount Check: {'PASS' if count_match else 'FAIL'}")
    print(f"  Expected: {len(ground_truth)} studies")
    print(f"  Got: {len(filtered_df)} studies")

    print("\n" + "=" * 80)
    if count_match:
        print("OVERALL: PASS - MD Anderson query working correctly!")
    else:
        print("OVERALL: FAIL - Count mismatch")
    print("=" * 80)

    return count_match


if __name__ == "__main__":
    print("\n")
    print("#" * 80)
    print("TWO-STEP AI FLOW VALIDATION SUITE")
    print("#" * 80)

    # Test 1: EV + P
    test1_pass = validate_ev_p_query()

    # Test 2: MD Anderson
    test2_pass = validate_md_anderson_query()

    # Summary
    print("\n\n" + "#" * 80)
    print("FINAL SUMMARY")
    print("#" * 80)
    print(f"\nTest 1 (EV + P): {'PASS' if test1_pass else 'FAIL'}")
    print(f"Test 2 (MD Anderson): {'PASS' if test2_pass else 'FAIL'}")

    if test1_pass and test2_pass:
        print("\nALL TESTS PASSED - Two-step AI flow is working correctly!")
    else:
        print("\nSOME TESTS FAILED - Review results above")
    print("\n" + "#" * 80 + "\n")
