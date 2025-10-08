"""
Improved Search Module
======================
Multi-field search with entity resolution, word boundaries, and suffix-aware matching.

Key Improvements:
1. Searches across ALL relevant fields (Title, Session, Theme, Speakers, Affiliation, etc.)
2. Uses entity resolver for normalization BEFORE search
3. Case-insensitive with word boundaries
4. Suffix-aware for drug variations (e.g., "enfortumab vedotin-ejfv")
5. Supports AND/OR logic with clarification
6. Optional fuzzy matching as backstop
"""

import pandas as pd
import re
from typing import List, Dict, Optional, Tuple
from functools import lru_cache

# Legacy entity_resolver imports removed - only used by smart_search() which is archived
# from entity_resolver import (
#     expand_query_entities,
#     build_drug_regex,
#     resolve_drug_name,
#     resolve_institution,
#     get_drug_search_patterns
# )

try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False


# ============================================================================
# SEARCH TEXT PRECOMPUTATION
# ============================================================================

def precompute_search_text(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create a concatenated 'search_text' field for each row.
    This field combines all searchable columns for efficient multi-field search.

    Columns included:
    - Title
    - Session
    - Theme
    - Speakers
    - Affiliation
    - Room
    - Date
    - Time
    - Speaker Location

    Returns:
        DataFrame with added 'search_text' and 'search_text_normalized' columns
    """
    df = df.copy()

    # Define searchable columns (in order of importance)
    searchable_columns = [
        'Title',
        'Session',
        'Theme',
        'Speakers',
        'Affiliation',
        'Speaker Location',
        'Room',
        'Date',
        'Time',
    ]

    # Only use columns that actually exist
    available_columns = [col for col in searchable_columns if col in df.columns]

    # Combine into single search text
    df['search_text'] = df[available_columns].fillna('').apply(
        lambda row: ' | '.join([str(val) for val in row if val]),
        axis=1
    )

    # Create normalized version (lowercase, for fast case-insensitive search)
    df['search_text_normalized'] = df['search_text'].str.lower()

    return df


# ============================================================================
# CORE SEARCH FUNCTIONS
# ============================================================================

def search_multi_field(
    df: pd.DataFrame,
    search_terms: List[str],
    logic: str = "OR",
    use_word_boundaries: bool = True,
    case_insensitive: bool = True
) -> pd.DataFrame:
    """
    Search across all fields using multiple search terms with AND/OR logic.

    Args:
        df: DataFrame with 'search_text' or 'search_text_normalized' column
        search_terms: List of terms to search for (should be canonical names from resolver)
        logic: "AND" or "OR" logic for combining terms
        use_word_boundaries: Use regex word boundaries (recommended)
        case_insensitive: Case-insensitive search (recommended)

    Returns:
        Filtered DataFrame with matching rows
    """
    if df.empty or not search_terms:
        return df

    # Ensure search_text exists
    if 'search_text' not in df.columns and 'search_text_normalized' not in df.columns:
        df = precompute_search_text(df)

    # Choose the appropriate search field
    search_field = 'search_text_normalized' if case_insensitive else 'search_text'

    if logic == "OR":
        # OR logic: match ANY term
        mask = pd.Series([False] * len(df), index=df.index)

        for term in search_terms:
            if use_word_boundaries:
                pattern = r'\b' + re.escape(term.lower() if case_insensitive else term) + r'\b'
                term_mask = df[search_field].str.contains(pattern, na=False, regex=True)
            else:
                term_mask = df[search_field].str.contains(
                    term.lower() if case_insensitive else term,
                    na=False,
                    regex=False
                )
            mask = mask | term_mask

        return df[mask]

    elif logic == "AND":
        # AND logic: match ALL terms
        mask = pd.Series([True] * len(df), index=df.index)

        for term in search_terms:
            if use_word_boundaries:
                pattern = r'\b' + re.escape(term.lower() if case_insensitive else term) + r'\b'
                term_mask = df[search_field].str.contains(pattern, na=False, regex=True)
            else:
                term_mask = df[search_field].str.contains(
                    term.lower() if case_insensitive else term,
                    na=False,
                    regex=False
                )
            mask = mask & term_mask

        return df[mask]

    else:
        raise ValueError(f"Invalid logic: {logic}. Must be 'AND' or 'OR'")


def search_with_drug_patterns(
    df: pd.DataFrame,
    drug_names: List[str],
    logic: str = "OR"
) -> pd.DataFrame:
    """
    Search for drugs using suffix-aware regex patterns.

    This handles variations like "enfortumab vedotin-ejfv".

    Args:
        df: DataFrame with search_text field
        drug_names: List of canonical drug names
        logic: "AND" or "OR"

    Returns:
        Filtered DataFrame
    """
    if df.empty or not drug_names:
        return df

    # Ensure search_text exists
    if 'search_text_normalized' not in df.columns:
        df = precompute_search_text(df)

    if logic == "OR":
        mask = pd.Series([False] * len(df), index=df.index)

        for drug in drug_names:
            drug_regex = build_drug_regex(drug, case_insensitive=True)
            drug_mask = df['search_text_normalized'].str.contains(drug_regex.pattern, na=False, regex=True)
            mask = mask | drug_mask

        return df[mask]

    elif logic == "AND":
        mask = pd.Series([True] * len(df), index=df.index)

        for drug in drug_names:
            drug_regex = build_drug_regex(drug, case_insensitive=True)
            drug_mask = df['search_text_normalized'].str.contains(drug_regex.pattern, na=False, regex=True)
            mask = mask & drug_mask

        return df[mask]

    else:
        raise ValueError(f"Invalid logic: {logic}")


def fuzzy_search_backstop(
    df: pd.DataFrame,
    search_terms: List[str],
    threshold: int = 90,
    search_columns: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Fuzzy matching backstop for when exact search returns zero results.

    Uses RapidFuzz to catch typos/mild misspellings.

    Args:
        df: DataFrame to search
        search_terms: Terms that returned no exact matches
        threshold: Fuzzy match threshold (90 = very close, 70 = lenient)
        search_columns: Columns to search (defaults to Title, Speakers, Affiliation)

    Returns:
        Filtered DataFrame with fuzzy matches
    """
    if not FUZZY_AVAILABLE:
        print("Warning: RapidFuzz not installed. Fuzzy search unavailable.")
        return pd.DataFrame()

    if df.empty or not search_terms:
        return pd.DataFrame()

    if search_columns is None:
        search_columns = ['Title', 'Speakers', 'Affiliation']

    # Filter to existing columns
    search_columns = [col for col in search_columns if col in df.columns]

    matches = []
    for idx, row in df.iterrows():
        for col in search_columns:
            cell_value = str(row[col]).lower()

            for term in search_terms:
                term_lower = term.lower()

                # Check if any word in the cell fuzzy-matches the term
                words = cell_value.split()
                for word in words:
                    score = fuzz.ratio(word, term_lower)
                    if score >= threshold:
                        matches.append(idx)
                        break

    # Remove duplicates and return
    unique_matches = list(set(matches))
    return df.loc[unique_matches]


# ============================================================================
# INTEGRATED SEARCH WITH ENTITY RESOLUTION
# ============================================================================

def smart_search(
    df: pd.DataFrame,
    user_query: str,
    ta_keywords: Optional[List[str]] = None,
    apply_fuzzy_backstop: bool = False,
    fuzzy_threshold: int = 90
) -> Tuple[pd.DataFrame, Dict]:
    """
    Main search function that integrates entity resolution + multi-field search.

    Workflow:
    1. Use entity resolver to expand query (drugs, institutions, logic)
    2. Check if clarification needed
    3. Apply TA filter (if provided)
    4. Search for drugs with suffix-aware patterns
    5. Search for institutions
    6. Optional: fuzzy backstop if zero results

    Args:
        df: Conference data DataFrame
        user_query: Raw user query
        ta_keywords: Optional list of TA keywords to filter by (e.g., ["bladder", "urothelial"])
        apply_fuzzy_backstop: Use fuzzy matching if exact search fails
        fuzzy_threshold: Fuzzy match threshold (90 recommended)

    Returns:
        Tuple of (filtered_df, metadata_dict)
        metadata_dict includes:
        - "needs_clarification": bool
        - "logic": "AND" or "OR" or "unclear"
        - "drugs_found": list
        - "institutions_found": list
        - "fuzzy_used": bool
    """
    # Precompute search text if not already done
    if 'search_text_normalized' not in df.columns:
        df = precompute_search_text(df)

    # Step 1: Resolve entities
    resolved = expand_query_entities(user_query)

    # Step 2: Check for clarification
    if resolved['needs_clarification']:
        return pd.DataFrame(), {
            "needs_clarification": True,
            "logic": resolved['logic'],
            "drugs_found": resolved['drugs'],
            "institutions_found": resolved['institutions'],
            "clarification_question": "Do you want studies with **both drugs together** (combination) or **either drug** (separate studies)?"
        }

    # Step 3: Apply TA filter (if provided)
    results = df.copy()
    if ta_keywords:
        ta_mask = pd.Series([False] * len(results), index=results.index)
        for keyword in ta_keywords:
            keyword_pattern = r'\b' + re.escape(keyword) + r'\b'
            ta_mask = ta_mask | results['search_text_normalized'].str.contains(keyword_pattern, na=False, regex=True)
        results = results[ta_mask]

    # Step 4: Search for drugs
    if resolved['drugs']:
        results = search_with_drug_patterns(
            results,
            drug_names=resolved['drugs'],
            logic=resolved['logic']
        )

    # Step 5: Search for institutions
    # Also search for the ORIGINAL abbreviation in case it appears as-is in data
    if resolved['institutions']:
        institution_terms = resolved['institutions'].copy()

        # Also add original abbreviations (e.g., "MSK" might appear in affiliation)
        # Extract potential abbreviations from query
        query_words = user_query.split()
        for word in query_words:
            word_lower = word.lower().strip('.,!?')
            if word_lower in ['msk', 'mskcc', 'mda', 'mdacc', 'dfci', 'jhu']:
                institution_terms.append(word)

        results = search_multi_field(
            results,
            search_terms=institution_terms,
            logic="OR"  # Institutions typically use OR logic
        )

    # Step 6: Fuzzy backstop
    fuzzy_used = False
    if apply_fuzzy_backstop and results.empty and resolved['drugs']:
        print(f"No exact matches found. Trying fuzzy search for: {resolved['drugs']}")
        results = fuzzy_search_backstop(df, resolved['drugs'], threshold=fuzzy_threshold)
        fuzzy_used = True

    metadata = {
        "needs_clarification": False,
        "logic": resolved['logic'],
        "drugs_found": resolved['drugs'],
        "institutions_found": resolved['institutions'],
        "ta_keywords_applied": ta_keywords,
        "fuzzy_used": fuzzy_used,
        "result_count": len(results)
    }

    return results, metadata


# ============================================================================
# HIGHLIGHTING FOR UI
# ============================================================================

def highlight_terms_in_results(df: pd.DataFrame, terms: List[str]) -> pd.DataFrame:
    """
    Add HTML <mark> highlighting to search results.

    Args:
        df: Results DataFrame
        terms: List of terms to highlight

    Returns:
        DataFrame with highlighted text
    """
    if df.empty or not terms:
        return df

    df_highlighted = df.copy()

    # Columns to highlight
    highlight_columns = ['Title', 'Speakers', 'Affiliation', 'Session', 'Theme']
    highlight_columns = [col for col in highlight_columns if col in df_highlighted.columns]

    for col in highlight_columns:
        for term in terms:
            pattern = re.escape(term)
            df_highlighted[col] = df_highlighted[col].astype(str).str.replace(
                f'({pattern})',
                r'<mark>\1</mark>',
                flags=re.IGNORECASE,
                regex=True
            )

    return df_highlighted


# ============================================================================
# MODULE SELF-TEST
# ============================================================================

if __name__ == "__main__":
    # Create test DataFrame
    test_data = pd.DataFrame({
        'Title': [
            'Pembrolizumab in advanced bladder cancer',
            'Atezolizumab + chemotherapy in urothelial carcinoma',
            'Enfortumab vedotin-ejfv combined with pembrolizumab',
            'Nivolumab monotherapy in renal cell carcinoma',
            'ADC strategies at MD Anderson Cancer Center'
        ],
        'Session': ['Oral', 'Poster', 'Oral', 'Oral', 'Educational'],
        'Theme': ['GU', 'GU', 'GU', 'GU', 'GU'],
        'Speakers': ['Smith J', 'Jones A', 'Lee K', 'Garcia M', 'Anderson R'],
        'Affiliation': ['MSK', 'Dana Farber', 'Johns Hopkins', 'Mayo Clinic', 'MD Anderson']
    })

    print("Improved Search Module Self-Test")
    print("=" * 60)

    # Test 1: Simple drug search
    print("\n1. Search: 'pembro in bladder cancer'")
    results, meta = smart_search(test_data, "pembro in bladder cancer", ta_keywords=["bladder", "urothelial"])
    print(f"   Results: {len(results)} studies")
    print(f"   Drugs found: {meta['drugs_found']}")
    print(f"   Titles: {results['Title'].tolist()}")

    # Test 2: Combination search
    print("\n2. Search: 'EV + pembro'")
    results, meta = smart_search(test_data, "EV + pembro")
    print(f"   Results: {len(results)} studies")
    print(f"   Logic: {meta['logic']}")
    print(f"   Drugs found: {meta['drugs_found']}")

    # Test 3: Ambiguous search
    print("\n3. Search: 'pembro and atezo'")
    results, meta = smart_search(test_data, "pembro and atezo")
    print(f"   Needs clarification: {meta['needs_clarification']}")
    if meta['needs_clarification']:
        print(f"   Question: {meta.get('clarification_question')}")

    # Test 4: Institution search
    print("\n4. Search: 'studies at MSK'")
    results, meta = smart_search(test_data, "studies at MSK")
    print(f"   Results: {len(results)} studies")
    print(f"   Institutions found: {meta['institutions_found']}")

    # Test 5: MOA expansion
    print("\n5. Search: 'ADC studies'")
    results, meta = smart_search(test_data, "ADC studies")
    print(f"   Results: {len(results)} studies")
    print(f"   Drugs found (expanded): {meta['drugs_found']}")
