"""
Query Intelligence Module (Tier 2)
===================================
Handles intent detection, field extraction, temporal filtering, and dynamic verbosity.

Addresses edge cases:
- "What room is the KEYNOTE-901 trial?" → factual_lookup, target_field=Room
- "Show me studies today on avelumab" → list_filtered, temporal_filter=today
- "Summarize EV + P combination trends" → synthesis, verbosity=detailed
"""

import re
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta


# ============================================================================
# INTENT CLASSIFICATION
# ============================================================================

def classify_query_intent(query: str, resolved_entities: dict) -> dict:
    """
    Detect user intent and required verbosity.

    Intent Types:
    - factual_lookup: "What room is X?" → Minimal response (direct answer)
    - list_filtered: "Show me X on date Y" → Quick response (bullet points)
    - synthesis: "Summarize X" → Detailed response (full analysis)
    - comparison: "Compare X vs Y" → Medium response (structured comparison)

    Args:
        query: User query string
        resolved_entities: Output from entity resolver

    Returns:
        Dict with intent, verbosity, expected_result_count
    """
    query_lower = query.lower()

    # Check for explicit user verbosity requests (highest priority)
    user_verbosity = None
    if re.search(r'\b(concise|brief|short|quick)\b', query_lower):
        user_verbosity = "quick"
    elif re.search(r'\b(comprehensive|detailed|in-depth|thorough|full)\b', query_lower):
        user_verbosity = "detailed"

    # Factual lookup patterns (specific field questions)
    factual_patterns = [
        r"what (room|time|date|session)",
        r"which room",
        r"when is",
        r"where is",
        r"who is presenting",
        r"who presents"
    ]

    # List patterns (enumeration requests)
    list_patterns = [
        r"show me",
        r"list (all|the)",
        r"which (studies|presentations|abstracts)",
        r"what (studies|presentations|abstracts)",
        r"get me",
        r"find (all|the)"
    ]

    # Synthesis patterns (analysis requests)
    synthesis_patterns = [
        r"summarize",
        r"what are the (trends|themes|findings|insights)",
        r"analyze",
        r"synthesize",
        r"tell me about",
        r"what do we know about"
    ]

    # Comparison patterns
    comparison_patterns = [
        r"compare",
        r"difference between",
        r"vs\.?",
        r"versus",
        r"compared to"
    ]

    # Check patterns in priority order
    for pattern in factual_patterns:
        if re.search(pattern, query_lower):
            return {
                "intent": "factual_lookup",
                "verbosity": user_verbosity or "minimal",
                "expected_result_count": 1,
                "requires_ai": False  # Can answer directly
            }

    for pattern in list_patterns:
        if re.search(pattern, query_lower):
            return {
                "intent": "list_filtered",
                "verbosity": user_verbosity or "quick",
                "expected_result_count": "multiple",
                "requires_ai": True  # AI gives brief summary
            }

    for pattern in comparison_patterns:
        if re.search(pattern, query_lower):
            return {
                "intent": "comparison",
                "verbosity": user_verbosity or "medium",
                "expected_result_count": 2,
                "requires_ai": True
            }

    for pattern in synthesis_patterns:
        if re.search(pattern, query_lower):
            return {
                "intent": "synthesis",
                "verbosity": user_verbosity or "detailed",
                "expected_result_count": "multiple",
                "requires_ai": True
            }

    # Default: Assume synthesis if drugs/topics mentioned
    if resolved_entities.get('drugs') or resolved_entities.get('institutions'):
        return {
            "intent": "synthesis",
            "verbosity": user_verbosity or "medium",
            "expected_result_count": "multiple",
            "requires_ai": True
        }

    # Fallback
    return {
        "intent": "list_filtered",
        "verbosity": user_verbosity or "quick",
        "expected_result_count": "multiple",
        "requires_ai": True
    }


# ============================================================================
# TARGET FIELD EXTRACTION
# ============================================================================

def extract_target_field(query: str) -> Optional[str]:
    """
    Extract which specific field user is asking about.

    Examples:
    - "What room is X?" → "Room"
    - "What time is Y?" → "Time"
    - "Who is presenting Z?" → "Speakers"

    Returns:
        Column name or None
    """
    query_lower = query.lower()

    field_patterns = {
        "Room": [r"what room", r"which room", r"where is", r"location of"],
        "Time": [r"what time", r"when is", r"at what time"],
        "Speakers": [r"who is presenting", r"who presents", r"presenters?", r"speaker"],
        "Date": [r"what date", r"which date", r"what day"],
        "Session": [r"what session", r"which session", r"session type"],
        "Affiliation": [r"which institution", r"what institution", r"from where", r"affiliation"],
        "Theme": [r"what theme", r"which theme", r"topic"]
    }

    for field, patterns in field_patterns.items():
        for pattern in patterns:
            if re.search(pattern, query_lower):
                return field

    return None


# ============================================================================
# TEMPORAL FILTER EXTRACTION
# ============================================================================

def parse_date_string(date_str: str, current_date: Optional[str] = None) -> Optional[str]:
    """
    Parse various date formats to standardized format.

    Examples:
    - "10/18" → "10/18/2025"
    - "Oct 18" → "10/18/2025"
    - "October 18" → "10/18/2025"
    """
    date_str = date_str.strip()

    # Try MM/DD format
    match = re.match(r'(\d{1,2})/(\d{1,2})', date_str)
    if match:
        month, day = match.groups()
        return f"{month}/{day}/2025"  # Assume 2025 for ESMO

    # Try "Oct 18" or "October 18"
    month_map = {
        'jan': '1', 'january': '1',
        'feb': '2', 'february': '2',
        'mar': '3', 'march': '3',
        'apr': '4', 'april': '4',
        'may': '5',
        'jun': '6', 'june': '6',
        'jul': '7', 'july': '7',
        'aug': '8', 'august': '8',
        'sep': '9', 'sept': '9', 'september': '9',
        'oct': '10', 'october': '10',
        'nov': '11', 'november': '11',
        'dec': '12', 'december': '12'
    }

    for month_name, month_num in month_map.items():
        pattern = rf'\b{month_name}\s+(\d{{1,2}})\b'
        match = re.search(pattern, date_str.lower())
        if match:
            day = match.group(1)
            return f"{month_num}/{day}/2025"

    return None


def extract_temporal_filter(query: str, current_date: Optional[str] = None) -> Optional[dict]:
    """
    Extract date/time filters from query.

    Examples:
    - "today" → current_date
    - "10/18" → "10/18/2025"
    - "tomorrow" → current_date + 1 day
    - "Oct 18" → "10/18/2025"

    Args:
        query: User query
        current_date: Current date in MM/DD/YYYY format (for "today", "tomorrow")

    Returns:
        Dict with temporal filter info or None
    """
    query_lower = query.lower()

    # Handle "today"
    if re.search(r'\btoday\b', query_lower):
        if current_date:
            return {
                "type": "specific_date",
                "date": current_date,
                "source": "today",
                "raw": "today"
            }

    # Handle "tomorrow"
    if re.search(r'\btomorrow\b', query_lower):
        if current_date:
            # Parse current_date and add 1 day
            try:
                dt = datetime.strptime(current_date, "%m/%d/%Y")
                tomorrow = dt + timedelta(days=1)
                return {
                    "type": "specific_date",
                    "date": tomorrow.strftime("%m/%d/%Y"),
                    "source": "tomorrow",
                    "raw": "tomorrow"
                }
            except:
                pass

    # Handle specific date patterns
    date_patterns = [
        r'(\d{1,2})/(\d{1,2})',  # 10/18
        r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\s+(\d{1,2})\b',
    ]

    for pattern in date_patterns:
        match = re.search(pattern, query_lower)
        if match:
            matched_str = match.group(0)
            parsed_date = parse_date_string(matched_str)
            if parsed_date:
                return {
                    "type": "specific_date",
                    "date": parsed_date,
                    "source": matched_str,
                    "raw": matched_str
                }

    return None


# ============================================================================
# TRIAL NAME RECOGNITION
# ============================================================================

def extract_trial_names(query: str) -> List[str]:
    """
    Extract clinical trial names from query.

    Common trial naming patterns:
    - KEYNOTE-XXX (Merck)
    - CheckMate-XXX (BMS)
    - IMvigor-XXX (Roche)
    - JAVELIN-XXX (Merck/Pfizer)
    - TROPICS-XXX (Gilead)
    - EV-XXX (Enfortumab vedotin trials)
    - COSMIC-XXX

    Examples:
    - "What room is KEYNOTE-901?" → ["KEYNOTE-901"]
    - "Tell me about EV-301 and TROPHY-U-01" → ["EV-301", "TROPHY-U-01"]
    """
    trial_patterns = [
        r'\b(KEYNOTE|CheckMate|IMvigor|JAVELIN|TROPICS|COSMIC|TROPHY|EV|ATLAS|CONTACT|DANUBE|MYSTIC|NEPTUNE|POUT|RANGE|SAUL|SPARTANS|SWOG|VESPER)-\d+[A-Z]?\b',
        r'\b[A-Z]{2,}-\d{3,4}\b',  # Generic: XX-XXX format
    ]

    trials = []
    for pattern in trial_patterns:
        matches = re.findall(pattern, query, re.IGNORECASE)
        trials.extend(matches)

    # Remove duplicates, preserve order
    seen = set()
    unique_trials = []
    for trial in trials:
        trial_upper = trial.upper()
        if trial_upper not in seen:
            seen.add(trial_upper)
            unique_trials.append(trial_upper)

    return unique_trials


# ============================================================================
# INTEGRATED QUERY ANALYSIS
# ============================================================================

def analyze_query(query: str, resolved_entities: dict, current_date: Optional[str] = None) -> dict:
    """
    Comprehensive query analysis combining all intelligence.

    Args:
        query: User query string
        resolved_entities: Output from entity_resolver.expand_query_entities()
        current_date: Current date for temporal filtering

    Returns:
        Complete analysis dict with:
        - intent, verbosity, requires_ai
        - target_field
        - temporal_filter
        - trial_names
        - original resolved_entities
    """
    # Intent classification
    intent_info = classify_query_intent(query, resolved_entities)

    # Field extraction
    target_field = extract_target_field(query)

    # Temporal extraction
    temporal_filter = extract_temporal_filter(query, current_date)

    # Trial name extraction
    trial_names = extract_trial_names(query)

    # Combine everything
    analysis = {
        "query": query,
        "intent": intent_info['intent'],
        "verbosity": intent_info['verbosity'],
        "requires_ai": intent_info['requires_ai'],
        "expected_result_count": intent_info['expected_result_count'],
        "target_field": target_field,
        "temporal_filter": temporal_filter,
        "trial_names": trial_names,
        "entities": resolved_entities  # Original entity resolution
    }

    return analysis


# ============================================================================
# RESPONSE FORMATTING BASED ON INTENT
# ============================================================================

def format_factual_response(results, target_field: str, query: str) -> dict:
    """
    Format response for factual lookups.

    Example:
    Query: "What room is KEYNOTE-901?"
    Returns: Direct answer + context + follow-up offer
    """
    if results.empty or target_field not in results.columns:
        return {
            "type": "factual_answer",
            "answer": f"I couldn't find information about the {target_field.lower()}.",
            "table": results,
            "ai_synthesis_needed": False
        }

    if len(results) == 1:
        # Single result - direct answer
        row = results.iloc[0]
        value = row[target_field]
        title = row.get('Title', 'this presentation')

        answer = f"**{target_field}:** {value}\n\n"

        # Add context based on field
        if target_field == "Room" and 'Time' in row and 'Speakers' in row:
            answer += f"📍 The presentation \"{title[:60]}...\" is at **{row['Time']}**, presented by **{row['Speakers']}**.\n\n"
        elif target_field == "Time" and 'Room' in row:
            answer += f"🕐 Scheduled for **{value}** in **{row['Room']}**.\n\n"
        elif target_field == "Speakers" and 'Affiliation' in row:
            answer += f"👤 From **{row['Affiliation']}**.\n\n"

        answer += "💡 Would you like more details about this study?"

        return {
            "type": "factual_answer",
            "answer": answer,
            "table": results[['Identifier', 'Title', target_field]],
            "ai_synthesis_needed": False
        }
    else:
        # Multiple results - show list
        answer = f"Found **{len(results)} presentations**:\n\n"
        answer += "[See table below]\n\n"
        answer += "💡 Please specify which presentation you're interested in, or ask for a synthesis."

        return {
            "type": "factual_answer_multiple",
            "answer": answer,
            "table": results[['Identifier', 'Title', target_field]],
            "ai_synthesis_needed": False
        }


def format_list_response(results, query: str, temporal_filter: Optional[dict] = None) -> dict:
    """
    Format response for list queries.

    Example:
    Query: "Show me all avelumab studies today"
    Returns: Count + table + synthesis offer
    """
    if results.empty:
        temporal_desc = f" {temporal_filter['source']}" if temporal_filter else ""
        return {
            "type": "list_filtered",
            "answer": f"No studies found{temporal_desc}.",
            "table": results,
            "ai_synthesis_needed": False
        }

    temporal_desc = f" on {temporal_filter['source']}" if temporal_filter else ""

    answer = f"**{len(results)} studies found{temporal_desc}:**\n\n"
    answer += "[See table below]\n\n"
    answer += "💡 Would you like me to synthesize key themes from these studies?"

    return {
        "type": "list_filtered",
        "answer": answer,
        "table": results,
        "ai_synthesis_needed": "optional"  # User can request
    }


# ============================================================================
# MODULE SELF-TEST
# ============================================================================

if __name__ == "__main__":
    from entity_resolver import expand_query_entities

    print("Query Intelligence Module Self-Test")
    print("=" * 70)

    test_cases = [
        {
            "query": "What room is the KEYNOTE-901 trial?",
            "current_date": "10/18/2025"
        },
        {
            "query": "Show me all avelumab studies today",
            "current_date": "10/18/2025"
        },
        {
            "query": "Which studies on 10/18 involve EV + pembrolizumab?",
            "current_date": "10/18/2025"
        },
        {
            "query": "Summarize the trends in ADC research",
            "current_date": None
        },
        {
            "query": "Compare pembrolizumab vs atezolizumab",
            "current_date": None
        }
    ]

    for i, test in enumerate(test_cases, 1):
        query = test['query']
        current_date = test['current_date']

        print(f"\n{i}. Query: \"{query}\"")
        print("-" * 70)

        # Entity resolution
        resolved = expand_query_entities(query)

        # Query analysis
        analysis = analyze_query(query, resolved, current_date)

        print(f"   Intent: {analysis['intent']}")
        print(f"   Verbosity: {analysis['verbosity']}")
        print(f"   Requires AI: {analysis['requires_ai']}")
        print(f"   Target Field: {analysis['target_field']}")
        print(f"   Temporal Filter: {analysis['temporal_filter']}")
        print(f"   Trial Names: {analysis['trial_names']}")
        print(f"   Drugs: {resolved['drugs']}")
        print(f"   Logic: {resolved['logic']}")
