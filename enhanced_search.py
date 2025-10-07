"""
Enhanced Search Module (Tier 2)
================================
Integrates all Tier 1 + Tier 2 improvements with comprehensive debug logging.

Complete workflow:
1. Entity resolution (drugs, institutions, combinations)
2. Query intelligence (intent, fields, temporal, trials)
3. Multi-field search
4. Dynamic response formatting
5. AI synthesis (when needed)
"""

import pandas as pd
from typing import Dict, Tuple, Optional, List
import logging
from datetime import datetime

from entity_resolver import expand_query_entities, build_drug_regex
from improved_search import smart_search, precompute_search_text, search_with_drug_patterns
from query_intelligence import (
    analyze_query,
    format_factual_response,
    format_list_response,
    extract_trial_names
)
from lean_synthesis import build_lean_synthesis_prompt, estimate_prompt_tokens


# ============================================================================
# DEBUG LOGGING CONFIGURATION
# ============================================================================

def setup_debug_logging(log_file: Optional[str] = None, console_level: str = "INFO"):
    """
    Configure debug logging for enhanced search.

    Args:
        log_file: Optional file path for log output
        console_level: Console logging level (DEBUG, INFO, WARNING, ERROR)
    """
    # Create logger
    logger = logging.getLogger('enhanced_search')
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers
    logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, console_level.upper()))
    console_format = logging.Formatter('[%(levelname)s] %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger


# Global logger
logger = setup_debug_logging(console_level="DEBUG")


# ============================================================================
# ENHANCED SEARCH WITH DEBUG LOGGING
# ============================================================================

def enhanced_search(
    df: pd.DataFrame,
    user_query: str,
    ta_keywords: Optional[List[str]] = None,
    current_date: Optional[str] = None,
    debug: bool = True
) -> Tuple[pd.DataFrame, Dict]:
    """
    Enhanced search with full Tier 1 + Tier 2 intelligence and debug logging.

    Args:
        df: DataFrame (must have search_text_normalized column)
        user_query: User query string
        ta_keywords: Optional TA filter keywords
        current_date: Current date for temporal filtering (MM/DD/YYYY)
        debug: Enable debug logging

    Returns:
        Tuple of (results_df, metadata_dict)
    """
    if debug:
        logger.info("=" * 70)
        logger.info(f"ENHANCED SEARCH START")
        logger.info(f"Query: '{user_query}'")
        logger.info(f"TA Filter: {ta_keywords}")
        logger.info(f"Current Date: {current_date}")
        logger.info("=" * 70)

    # Step 1: Entity Resolution
    if debug:
        logger.info("\n[STEP 1] Entity Resolution")

    resolved = expand_query_entities(user_query)

    if debug:
        logger.debug(f"  Drugs found: {resolved['drugs']}")
        logger.debug(f"  Institutions: {resolved['institutions']}")
        logger.debug(f"  TA keywords: {resolved['ta_keywords']}")
        logger.debug(f"  Logic: {resolved['logic']}")
        logger.debug(f"  Needs clarification: {resolved['needs_clarification']}")

    # Step 2: Query Intelligence
    if debug:
        logger.info("\n[STEP 2] Query Intelligence")

    analysis = analyze_query(user_query, resolved, current_date)

    if debug:
        logger.debug(f"  Intent: {analysis['intent']}")
        logger.debug(f"  Verbosity: {analysis['verbosity']}")
        logger.debug(f"  Requires AI: {analysis['requires_ai']}")
        logger.debug(f"  Target field: {analysis['target_field']}")
        logger.debug(f"  Temporal filter: {analysis['temporal_filter']}")
        logger.debug(f"  Trial names: {analysis['trial_names']}")

    # Step 3: Check for clarification
    if resolved['needs_clarification']:
        if debug:
            logger.warning("\n[CLARIFICATION NEEDED]")
            logger.warning(f"  Question: Do you want AND (combination) or OR (either drug)?")

        return pd.DataFrame(), {
            "needs_clarification": True,
            "clarification_question": "Do you want studies with **both drugs together** (combination) or **either drug** (separate studies)?",
            "analysis": analysis,
            "resolved": resolved
        }

    # Step 4: Multi-Field Search
    if debug:
        logger.info("\n[STEP 3] Multi-Field Search")
        logger.debug(f"  Input dataset: {len(df)} rows")

    # Ensure search_text exists
    if 'search_text_normalized' not in df.columns:
        if debug:
            logger.debug("  Precomputing search_text...")
        df = precompute_search_text(df)

    results = df.copy()

    # Apply TA filter first
    if ta_keywords:
        if debug:
            logger.debug(f"  Applying TA filter: {ta_keywords}")

        ta_mask = pd.Series([False] * len(results), index=results.index)
        for keyword in ta_keywords:
            keyword_pattern = r'\b' + keyword.lower() + r'\b'
            ta_mask = ta_mask | results['search_text_normalized'].str.contains(keyword_pattern, na=False, regex=True)

        results = results[ta_mask]

        if debug:
            logger.debug(f"  After TA filter: {len(results)} rows")

    # Search for drugs
    if resolved['drugs']:
        if debug:
            logger.debug(f"  Searching for drugs: {resolved['drugs']} (logic: {resolved['logic']})")

        results = search_with_drug_patterns(
            results,
            drug_names=resolved['drugs'],
            logic=resolved['logic']
        )

        if debug:
            logger.debug(f"  After drug filter: {len(results)} rows")

    # Search for institutions
    if resolved['institutions']:
        if debug:
            logger.debug(f"  Searching for institutions: {resolved['institutions']}")

        from improved_search import search_multi_field

        # Also search for original abbreviations
        institution_terms = resolved['institutions'].copy()
        query_words = user_query.split()
        for word in query_words:
            word_lower = word.lower().strip('.,!?')
            if word_lower in ['msk', 'mskcc', 'mda', 'mdacc', 'dfci', 'jhu']:
                institution_terms.append(word)

        results = search_multi_field(
            results,
            search_terms=institution_terms,
            logic="OR"
        )

        if debug:
            logger.debug(f"  After institution filter: {len(results)} rows")

    # Search for trial names
    if analysis['trial_names']:
        if debug:
            logger.debug(f"  Searching for trial names: {analysis['trial_names']}")

        from improved_search import search_multi_field

        results = search_multi_field(
            results,
            search_terms=analysis['trial_names'],
            logic="OR"
        )

        if debug:
            logger.debug(f"  After trial name filter: {len(results)} rows")

    # Apply temporal filter
    if analysis['temporal_filter'] and 'Date' in results.columns:
        temporal_date = analysis['temporal_filter']['date']

        if debug:
            logger.debug(f"  Applying temporal filter: {temporal_date}")

        results = results[results['Date'] == temporal_date]

        if debug:
            logger.debug(f"  After temporal filter: {len(results)} rows")

    # Step 5: Results Summary
    if debug:
        logger.info(f"\n[STEP 4] Search Results: {len(results)} studies found")

        if len(results) > 0:
            logger.debug(f"  Sample results:")
            for idx, row in results.head(3).iterrows():
                identifier = row.get('Identifier', 'N/A')
                title = row.get('Title', 'No title')
                logger.debug(f"    - {identifier}: {title[:70]}...")

    # Step 6: Build metadata
    metadata = {
        "needs_clarification": False,
        "result_count": len(results),
        "analysis": analysis,
        "resolved": resolved,
        "ta_keywords_applied": ta_keywords,
        "search_stats": {
            "drugs_searched": resolved['drugs'],
            "institutions_searched": resolved['institutions'],
            "trial_names_searched": analysis['trial_names'],
            "logic_used": resolved['logic'],
            "temporal_filter_applied": analysis['temporal_filter'] is not None
        }
    }

    if debug:
        logger.info(f"\n[STEP 5] Metadata Complete")
        logger.debug(f"  Intent: {analysis['intent']}")
        logger.debug(f"  Verbosity: {analysis['verbosity']}")
        logger.debug(f"  Result count: {len(results)}")

    return results, metadata


# ============================================================================
# DYNAMIC RESPONSE GENERATION
# ============================================================================

def generate_response(
    user_query: str,
    results: pd.DataFrame,
    metadata: Dict,
    debug: bool = True
) -> Dict:
    """
    Generate appropriate response based on intent and results.

    Returns:
        Dict with:
        - type: response type
        - answer: text answer (if applicable)
        - table: results table
        - ai_synthesis_needed: bool or "optional"
        - prompt: AI prompt (if synthesis needed)
    """
    analysis = metadata['analysis']
    intent = analysis['intent']
    target_field = analysis['target_field']
    temporal_filter = analysis['temporal_filter']

    if debug:
        logger.info(f"\n[STEP 6] Response Generation")
        logger.debug(f"  Intent: {intent}")
        logger.debug(f"  Result count: {len(results)}")

    # Case 1: Factual lookup (specific field question)
    if intent == "factual_lookup" and target_field:
        if debug:
            logger.debug(f"  Generating factual response for field: {target_field}")

        response = format_factual_response(results, target_field, user_query)

        if debug:
            logger.info(f"  Response type: {response['type']}")
            logger.info(f"  AI synthesis needed: {response['ai_synthesis_needed']}")

        return response

    # Case 2: List filtered (simple enumeration)
    elif intent == "list_filtered":
        if debug:
            logger.debug(f"  Generating list response")

        response = format_list_response(results, user_query, temporal_filter)

        if debug:
            logger.info(f"  Response type: {response['type']}")
            logger.info(f"  AI synthesis needed: {response['ai_synthesis_needed']}")

        return response

    # Case 3: Synthesis or comparison (use AI)
    else:
        if debug:
            logger.debug(f"  Generating AI synthesis response")

        if results.empty:
            return {
                "type": "no_results",
                "answer": "No studies found matching your criteria.",
                "table": results,
                "ai_synthesis_needed": False
            }

        # Build lean synthesis prompt
        prompt = build_lean_synthesis_prompt(
            user_query=user_query,
            results_df=results,
            search_metadata=metadata['search_stats'],
            verbosity=analysis['verbosity']
        )

        tokens = estimate_prompt_tokens(prompt)

        if debug:
            logger.info(f"  AI synthesis prompt generated")
            logger.debug(f"    Prompt length: {len(prompt)} chars")
            logger.debug(f"    Estimated tokens: {tokens}")
            logger.debug(f"    Verbosity: {analysis['verbosity']}")

        return {
            "type": "ai_synthesis",
            "table": results,
            "prompt": prompt,
            "ai_synthesis_needed": True,
            "prompt_tokens": tokens,
            "verbosity": analysis['verbosity']
        }


# ============================================================================
# COMPLETE PIPELINE
# ============================================================================

def complete_search_pipeline(
    df: pd.DataFrame,
    user_query: str,
    ta_keywords: Optional[List[str]] = None,
    current_date: Optional[str] = None,
    debug: bool = True,
    log_file: Optional[str] = None
) -> Dict:
    """
    Complete search pipeline from query to response.

    Args:
        df: Conference data DataFrame
        user_query: User query
        ta_keywords: TA filter keywords
        current_date: Current date for temporal filtering
        debug: Enable debug logging
        log_file: Optional log file path

    Returns:
        Complete response dict ready for UI
    """
    # Setup logging
    if log_file:
        global logger
        logger = setup_debug_logging(log_file=log_file, console_level="DEBUG" if debug else "INFO")

    # Enhanced search
    results, metadata = enhanced_search(
        df=df,
        user_query=user_query,
        ta_keywords=ta_keywords,
        current_date=current_date,
        debug=debug
    )

    # Handle clarification
    if metadata.get('needs_clarification'):
        return {
            "status": "clarification_needed",
            "question": metadata['clarification_question'],
            "metadata": metadata
        }

    # Generate response
    response = generate_response(
        user_query=user_query,
        results=results,
        metadata=metadata,
        debug=debug
    )

    # Add metadata
    response['metadata'] = metadata

    if debug:
        logger.info(f"\n{'='*70}")
        logger.info(f"PIPELINE COMPLETE")
        logger.info(f"  Status: {response.get('type', 'unknown')}")
        logger.info(f"  Results: {len(results)} studies")
        logger.info(f"  AI synthesis: {response.get('ai_synthesis_needed', False)}")
        logger.info(f"{'='*70}\n")

    return response


# ============================================================================
# MODULE SELF-TEST
# ============================================================================

if __name__ == "__main__":
    print("Enhanced Search Module Self-Test")
    print("=" * 70)

    # Load test data
    try:
        df = pd.read_csv("ESMO_2025_FINAL_20250929.csv", nrows=500)
        print(f"\n[OK] Loaded {len(df)} ESMO studies")

        # Precompute search_text
        df = precompute_search_text(df)
        print(f"[OK] Search text precomputed")

    except FileNotFoundError:
        print("[ERROR] ESMO CSV not found")
        exit(1)

    # Test case: EV + P combination in bladder cancer
    print("\n" + "=" * 70)
    print("TEST: 'Show me all studies on EV + P combination'")
    print("(Bladder filter applied)")
    print("=" * 70)

    response = complete_search_pipeline(
        df=df,
        user_query="Show me all studies on the combination of EV + P",
        ta_keywords=["bladder", "urothelial"],
        current_date="10/18/2025",
        debug=True
    )

    print("\n[RESULTS]")
    print(f"  Status: {response.get('type')}")
    print(f"  Studies found: {len(response.get('table', []))}")
    print(f"  AI synthesis needed: {response.get('ai_synthesis_needed')}")

    if response.get('prompt'):
        print(f"  Prompt tokens: {response.get('prompt_tokens')}")
