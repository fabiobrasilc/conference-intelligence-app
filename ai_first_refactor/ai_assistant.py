"""
AI-First Chat Assistant for Conference Intelligence
====================================================

THE CORRECT FLOW (ENGRAVED):
1. AI receives query and interprets what user wants
2. AI generates keywords - handles acronyms, abbreviations using pharmaceutical knowledge
3. Keywords passed to DataFrame filtering - lightning fast pandas/regex on 4,686 rows
   - Sequential filtering if needed: date → drug → TA, etc.
   - Result: 4,686 → 30 (or however many match)
4. Table with filtered results generated
5. Filtered data passed BACK to AI for analysis
6. AI generates output based on filtered results and user's query

Two AI calls:
- Call 1: Query interpretation → Generate search keywords
- Call 2: Analyze filtered results → Generate response
"""

import pandas as pd
from typing import Dict, List, Any, Generator
import re
from openai import OpenAI
import os
import json


def handle_chat_query(
    df: pd.DataFrame,
    user_query: str,
    active_filters: Dict[str, List[str]],
    conversation_history: List[Dict[str, str]] = None,
    thinking_mode: str = "auto",
    active_ta: str = None,
    latest_report: str = None
) -> Dict[str, Any]:
    """
    SIMPLIFIED Main chat handler - Just extract keywords and filter.

    Step 1: AI extracts search keywords from query + conversation history
    Step 2: Filter DataFrame using keywords
    Step 3: AI analyzes filtered results with full conversation context

    The AI handles greetings, confirmations, and strategic questions naturally
    using conversation history. No hardcoded classification logic needed.
    """

    if conversation_history is None:
        conversation_history = []

    print(f"\n{'='*70}")
    print(f"[SIMPLIFIED] User query: {user_query}")
    print(f"[SIMPLIFIED] Starting dataset: {len(df)} studies")
    print(f"[SIMPLIFIED] Conversation history: {len(conversation_history)} previous exchanges")
    print(f"{'='*70}")

    # STEP 1: AI extracts search keywords (no classification, just keywords!)
    print(f"\n[STEP 1] AI extracting search keywords...")
    keywords = extract_simple_keywords(user_query, len(df), active_filters, conversation_history)

    print(f"[STEP 1] Extracted keywords:")
    has_keywords = False
    for key, values in keywords.items():
        if values:
            print(f"  {key}: {values}")
            has_keywords = True

    # Check if AI returned empty keywords (greeting, off-topic, or conceptual question with no entities)
    if not has_keywords:
        print(f"[STEP 1] No search keywords extracted - query is greeting/off-topic/conceptual")
        print(f"[STEP 2] Skipping filtering - will respond without studies")
        filtered_df = pd.DataFrame()  # Empty DataFrame - no studies to analyze
    else:
        # STEP 2: Filter DataFrame using keywords
        print(f"\n[STEP 2] Filtering dataset...")
        filtered_df = filter_dataframe_with_keywords(df, keywords)
        print(f"[STEP 2] Filtered: {len(df)} -> {len(filtered_df)} studies")

    # STEP 3: AI analyzes filtered results (handles greetings, confirmations, strategic questions naturally)
    print(f"\n[STEP 3] AI analyzing {len(filtered_df)} filtered studies...")
    response_generator = analyze_filtered_results_with_ai(
        user_query=user_query,
        filtered_df=filtered_df,
        original_count=len(df),
        active_filters=active_filters,
        extracted_keywords=keywords,
        thinking_mode=thinking_mode,
        conversation_history=conversation_history,
        active_ta=active_ta,
        latest_report=latest_report
    )

    return {
        'type': 'ai_response',
        'filtered_data': filtered_df,
        'response_stream': response_generator
    }


def extract_simple_keywords(
    user_query: str,
    dataset_size: int,
    active_filters: Dict,
    conversation_history: List[Dict[str, str]] = None
) -> Dict[str, List[str]]:
    """
    SIMPLIFIED STEP 1: AI extracts search keywords ONLY (no classification).

    NO classification logic - just extract keywords and let the second AI call
    handle greetings, confirmations, and strategic questions naturally.

    Args:
        user_query: User's raw question
        dataset_size: Number of studies currently visible
        active_filters: Active UI filters for context
        conversation_history: Previous exchanges (for "Yes" confirmations, etc.)

    Returns:
        Dict with keyword lists: {"drugs": [...], "dates": [...], "search_terms": [...]}
    """

    if conversation_history is None:
        conversation_history = []

    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    # Build filter context
    filter_parts = []
    if active_filters.get('ta'):
        filter_parts.append(f"{', '.join(active_filters['ta'])}")
    if active_filters.get('drug'):
        filter_parts.append(f"{', '.join(active_filters['drug'])}")
    filter_context = " about " + " and ".join(filter_parts) if filter_parts else ""

    # Build conversation history (for "Yes" confirmations)
    history_context = ""
    if conversation_history:
        history_context = "\n\n**CONVERSATION HISTORY (last 3 exchanges):**\n"
        for i, exchange in enumerate(conversation_history[-3:], 1):
            history_context += f"\n--- Exchange {i} ---\n"
            history_context += f"User: {exchange.get('user', '')}\n"
            history_context += f"Assistant: {exchange.get('assistant', '')[:200]}...\n"

    system_prompt = f"""You are a pharmaceutical keyword extractor for conference search.

**CONTEXT:**
- User is viewing {dataset_size} studies{filter_context} from ESMO 2025
- Your ONLY job: Extract search keywords from the user's query

**KEYWORD EXTRACTION RULES:**

1. **Date format conversion** - CRITICAL for matching dataset:
   - Dataset uses US format: MM/DD/YYYY (e.g., "10/18/2025")
   - If user query contains a date in ANY format, convert to MM/DD/YYYY:
     * "10/18" → "10/18/2025" (add year 2025)
     * "10/18/2025" → "10/18/2025" (already correct)
     * "18/10" (DD/MM) → "10/18/2025" (swap to MM/DD and add year)
     * "18/10/2025" (DD/MM/YYYY) → "10/18/2025" (swap to MM/DD/YYYY)
     * "2025-10-18" (ISO) → "10/18/2025" (convert to MM/DD/YYYY)
   - If day > 12, it MUST be DD/MM format - swap to MM/DD
   - Always return dates in "dates" field as MM/DD/YYYY format

2. **Drug abbreviations** - expand to full names:
   - "EV" → enfortumab vedotin
   - "P" / "pembro" → pembrolizumab
   - "Nivo" → nivolumab
   - "Atezo" → atezolizumab
   - For combinations ("EV + P"), provide BOTH drugs

2. **Confirmation responses** ("Yes", "Yes and..."):
   - CRITICAL: If user says "Yes" or "Yes and...", look at conversation history
   - Extract ALL keywords/terms mentioned in the PREVIOUS ASSISTANT MESSAGE
   - Example: Previous assistant said "broaden to: burnout, wellbeing, workforce" → User says "Yes" → Extract: ["burnout", "wellbeing", "workforce"]
   - Example: Previous assistant said "Would you like studies about EV+P?" → User says "Yes" → Extract: ["enfortumab vedotin", "pembrolizumab"]
   - If user says "Yes" but conversation history is empty or unclear, return empty keywords

3. **Molecular entities** - put in search_terms:
   - "METex14", "MET exon 14 skipping", "EGFR L858R", "HER2", "PD-L1", "KRAS G12C"

4. **Generic terms to EXCLUDE** (too broad):
   - ❌ "metastatic", "perioperative", "neoadjuvant", "adjuvant", "first-line", "1L", "2L"
   - ❌ Single letters: "P", "E", "V" (unless part of abbreviation like "EV+P")
   - ❌ TA names already in active filters: "bladder cancer", "NSCLC"

5. **Empty keywords** - If user is just greeting or asking a conceptual question with NO specific entities:
   - Return empty lists for all fields
   - The second AI call will handle greetings/conceptual answers naturally

**OUTPUT FORMAT:**
Return ONLY valid JSON in this exact format:
{{
  "drug_combinations": [
    ["drug1", "drug2"],
    ["drug3"]
  ],
  "drug_classes": ["ADC", "checkpoint inhibitor"],
  "therapeutic_areas": ["therapeutic area"],
  "institutions": ["institution name"],
  "dates": ["date"],
  "speakers": ["speaker name"],
  "search_terms": ["biomarker", "term"]
}}

**CRITICAL - Drug Combination Logic:**
- "drug_combinations" is an array of arrays - each inner array is a treatment group
- Drugs in the SAME inner array = AND logic (must appear together, e.g., combination regimen)
- Drugs in DIFFERENT inner arrays = OR logic (alternative options)

Examples:
* "EV + P studies" → {{"drug_combinations": [["enfortumab vedotin", "pembrolizumab"]]}}
  → Finds studies with BOTH enfortumab vedotin AND pembrolizumab

* "avelumab studies" → {{"drug_combinations": [["avelumab"]]}}
  → Finds studies with avelumab

* "EV+P vs avelumab" or "EV+P or avelumab" → {{"drug_combinations": [["enfortumab vedotin", "pembrolizumab"], ["avelumab"]]}}
  → Finds studies with (enfortumab vedotin AND pembrolizumab) OR (avelumab)

* "Compare tepotinib, capmatinib, and crizotinib" → {{"drug_combinations": [["tepotinib"], ["capmatinib"], ["crizotinib"]]}}
  → Finds studies with tepotinib OR capmatinib OR crizotinib

* "Platinum followed by avelumab" → {{"drug_combinations": [["platinum", "avelumab"]]}}
  → Sequential regimen = treat as combination (AND logic)

Use your pharmaceutical knowledge to identify combination regimens vs alternatives!

Return ONLY JSON, no other text."""

    combined_prompt = f"""{system_prompt}{history_context}

USER QUERY: "{user_query}"

**Examples:**

Greeting (NO keywords needed):
"Hello!" → {{"drug_combinations": [], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": [], "speakers": [], "search_terms": []}}

Date format conversion:
"What are all the bladder poster presentations happening on 10/18?" → {{"drug_combinations": [], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": ["10/18/2025"], "speakers": [], "search_terms": []}}

Date format conversion (international):
"What are all the bladder poster presentations happening on 18/10?" → {{"drug_combinations": [], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": ["10/18/2025"], "speakers": [], "search_terms": []}}

Drug abbreviation (combination):
"EV + P studies" → {{"drug_combinations": [["enfortumab vedotin", "pembrolizumab"]], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": [], "speakers": [], "search_terms": []}}

Comparison query (combination vs alternative):
"EV+P vs avelumab" → {{"drug_combinations": [["enfortumab vedotin", "pembrolizumab"], ["avelumab"]], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": [], "speakers": [], "search_terms": []}}

Confirmation response (extract keywords from PREVIOUS assistant message):
User: "Yes" (previous assistant message was: "Would you like to broaden to keywords: burnout, wellbeing, workforce?") → {{"drug_combinations": [], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": [], "speakers": [], "search_terms": ["burnout", "wellbeing", "workforce"]}}

Another confirmation example:
User: "Yes" (previous assistant message mentioned "EV+P studies") → {{"drug_combinations": [["enfortumab vedotin", "pembrolizumab"]], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": [], "speakers": [], "search_terms": []}}

Molecular entity:
"METex14 skipping" → {{"drug_combinations": [], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": [], "speakers": [], "search_terms": ["METex14", "MET exon 14 skipping"]}}

Conceptual question (NO specific entities):
"What is the difference between PD-1 and PD-L1?" → {{"drug_combinations": [], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": [], "speakers": [], "search_terms": []}}

Now extract keywords from the user query above. Return ONLY valid JSON."""

    try:
        print(f"[SIMPLIFIED EXTRACTION] Calling GPT-5 API...")
        response = client.responses.create(
            model="gpt-5-mini",
            input=combined_prompt,
            reasoning={"effort": "low"},  # Simple keyword extraction
            text={"verbosity": "low"},
            max_output_tokens=1000
        )

        response_text = response.output_text if hasattr(response, 'output_text') else ""
        print(f"[SIMPLIFIED EXTRACTION] Response: {response_text[:200]}")

        if not response_text.strip():
            print(f"[SIMPLIFIED EXTRACTION] Empty response - returning empty keywords")
            return {
                "drug_combinations": [],
                "drug_classes": [],
                "therapeutic_areas": [],
                "institutions": [],
                "dates": [],
                "speakers": [],
                "search_terms": []
            }

        keywords = json.loads(response_text.strip())

        # Backward compatibility: convert old "drugs" format to "drug_combinations"
        if "drugs" in keywords and "drug_combinations" not in keywords:
            # Old format: ["drug1", "drug2"] → New format: [["drug1"], ["drug2"]] (OR logic)
            keywords["drug_combinations"] = [[drug] for drug in keywords["drugs"]]
            del keywords["drugs"]

        return keywords

    except json.JSONDecodeError as e:
        print(f"[SIMPLIFIED EXTRACTION ERROR] Invalid JSON: {e}")
        print(f"[SIMPLIFIED EXTRACTION ERROR] Response: {response_text[:200]}")
        return {
            "drug_combinations": [],
            "drug_classes": [],
            "therapeutic_areas": [],
            "institutions": [],
            "dates": [],
            "speakers": [],
            "search_terms": []
        }
    except Exception as e:
        print(f"[SIMPLIFIED EXTRACTION ERROR] {e}")
        import traceback
        traceback.print_exc()
        return {
            "drug_combinations": [],
            "drug_classes": [],
            "therapeutic_areas": [],
            "institutions": [],
            "dates": [],
            "speakers": [],
            "search_terms": []
        }


def filter_dataframe_with_keywords(
    df: pd.DataFrame,
    keywords: Dict[str, List[str]]
) -> pd.DataFrame:
    """
    STEP 2: Filter DataFrame using AI-generated keywords.

    Uses pandas/regex for lightning-fast filtering.
    Sequential filtering: date → drugs → TA → institutions → etc.

    Args:
        df: Full dataset
        keywords: AI-generated search keywords

    Returns:
        Filtered DataFrame
    """

    filtered = df.copy()
    original_count = len(filtered)

    # Sequential filtering (most restrictive first)

    # 1. Filter by date (if specified)
    # Note: AI is instructed to convert dates to MM/DD/YYYY format to match dataset
    if keywords.get('dates'):
        date_pattern = '|'.join([re.escape(d) for d in keywords['dates']])
        filtered = filtered[
            filtered['Date'].str.contains(date_pattern, case=False, na=False, regex=True)
        ]
        print(f"  After date filter: {len(filtered)} studies")

    # 2. Filter by institutions (if specified)
    # Search BOTH Affiliation and Speaker Location columns
    if keywords.get('institutions'):
        inst_pattern = '|'.join([re.escape(inst) for inst in keywords['institutions']])

        # Check which columns are available
        affiliation_match = filtered['Affiliation'].str.contains(inst_pattern, case=False, na=False, regex=True)

        if 'Speaker Location' in filtered.columns:
            speaker_location_match = filtered['Speaker Location'].str.contains(inst_pattern, case=False, na=False, regex=True)
            # Match if found in EITHER Affiliation OR Speaker Location
            filtered = filtered[affiliation_match | speaker_location_match]
        else:
            # Fallback to Affiliation only if Speaker Location not available
            filtered = filtered[affiliation_match]

        print(f"  After institution filter (Affiliation OR Speaker Location): {len(filtered)} studies")

    # 3. Filter by drug combinations (if specified)
    if keywords.get('drug_combinations'):
        # Smart AND/OR logic:
        # - Within a combination (inner array): AND logic (all drugs must be present)
        # - Between combinations (different arrays): OR logic (studies matching ANY combination)

        combination_results = []

        for combo in keywords['drug_combinations']:
            combo_filtered = filtered.copy()

            if len(combo) == 1:
                # Single drug - simple filter
                drug_pattern = re.escape(combo[0])
                if 'search_text_normalized' in combo_filtered.columns:
                    combo_filtered = combo_filtered[
                        combo_filtered['search_text_normalized'].str.contains(
                            drug_pattern, case=False, na=False, regex=True
                        )
                    ]
                else:
                    combo_filtered = combo_filtered[
                        combo_filtered['Title'].str.contains(drug_pattern, case=False, na=False, regex=True)
                    ]
                print(f"  Combination [{combo[0]}]: {len(combo_filtered)} studies")
            else:
                # Multiple drugs - AND logic (all must be present)
                for drug in combo:
                    drug_pattern = re.escape(drug)
                    if 'search_text_normalized' in combo_filtered.columns:
                        combo_filtered = combo_filtered[
                            combo_filtered['search_text_normalized'].str.contains(
                                drug_pattern, case=False, na=False, regex=True
                            )
                        ]
                    else:
                        combo_filtered = combo_filtered[
                            combo_filtered['Title'].str.contains(drug_pattern, case=False, na=False, regex=True)
                        ]
                print(f"  Combination [{' + '.join(combo)}]: {len(combo_filtered)} studies after AND filter")

            combination_results.append(combo_filtered)

        # Union all combination results (OR between combinations)
        if combination_results:
            filtered = pd.concat(combination_results).drop_duplicates()
            print(f"  After drug combination filter (OR between {len(keywords['drug_combinations'])} groups): {len(filtered)} studies")

    # 4. Filter by drug classes (if specified and no specific drug combinations)
    if keywords.get('drug_classes') and not keywords.get('drug_combinations'):
        class_pattern = '|'.join([re.escape(c) for c in keywords['drug_classes']])
        if 'search_text_normalized' in filtered.columns:
            filtered = filtered[
                filtered['search_text_normalized'].str.contains(
                    class_pattern, case=False, na=False, regex=True
                )
            ]
        else:
            filtered = filtered[
                filtered['Title'].str.contains(class_pattern, case=False, na=False, regex=True)
            ]
        print(f"  After drug class filter: {len(filtered)} studies")

    # 5. Filter by therapeutic areas (if specified)
    if keywords.get('therapeutic_areas'):
        ta_pattern = '|'.join([re.escape(ta) for ta in keywords['therapeutic_areas']])
        if 'search_text_normalized' in filtered.columns:
            filtered = filtered[
                filtered['search_text_normalized'].str.contains(
                    ta_pattern, case=False, na=False, regex=True
                )
            ]
        else:
            filtered = filtered[
                (filtered['Title'].str.contains(ta_pattern, case=False, na=False, regex=True)) |
                (filtered['Theme'].str.contains(ta_pattern, case=False, na=False, regex=True))
            ]
        print(f"  After TA filter: {len(filtered)} studies")

    # 6. Filter by speakers (if specified) - Use fuzzy/partial matching
    if keywords.get('speakers'):
        # For each speaker name, extract last name and first name parts
        # Match on: last name + at least first letter of first name
        # This handles "Cindy J. Jiang" → "Cindy Y. Jiang" mismatches
        speaker_patterns = []
        for speaker in keywords['speakers']:
            # Split name into parts
            parts = speaker.strip().split()
            if len(parts) >= 2:
                # Last part is last name, first part is first name
                first_name = parts[0]
                last_name = parts[-1]
                # Match: last name + first letter of first name (case-insensitive)
                # Example: "Jiang" AND "C" matches "Cindy Y. Jiang" or "Cindy J. Jiang"
                pattern = f"(?=.*{re.escape(last_name)})(?=.*{re.escape(first_name[0])})"
                speaker_patterns.append(pattern)
            else:
                # Single word - just match that word
                speaker_patterns.append(re.escape(speaker))

        # Combine all speaker patterns with OR
        combined_pattern = '|'.join(speaker_patterns)
        filtered = filtered[
            filtered['Speakers'].str.contains(combined_pattern, case=False, na=False, regex=True)
        ]
        print(f"  After speaker filter (fuzzy): {len(filtered)} studies")

    # 7. Filter by additional search terms (if specified)
    # NOTE: Only apply if we don't already have drug-based filtering
    # This prevents over-filtering when drugs already imply the context
    if keywords.get('search_terms') and not keywords.get('drug_combinations'):
        term_pattern = '|'.join([re.escape(t) for t in keywords['search_terms']])
        if 'search_text_normalized' in filtered.columns:
            filtered = filtered[
                filtered['search_text_normalized'].str.contains(
                    term_pattern, case=False, na=False, regex=True
                )
            ]
        else:
            filtered = filtered[
                filtered['Title'].str.contains(term_pattern, case=False, na=False, regex=True)
            ]
        print(f"  After search terms filter: {len(filtered)} studies")

    print(f"  Final: {original_count} -> {len(filtered)} studies")

    return filtered


def analyze_filtered_results_with_ai(
    user_query: str,
    filtered_df: pd.DataFrame,
    original_count: int,
    active_filters: Dict[str, List[str]],
    extracted_keywords: Dict[str, List[str]] = None,
    thinking_mode: str = "auto",
    conversation_history: List[Dict[str, str]] = None,
    active_ta: str = None,
    latest_report: str = None
) -> Generator[str, None, None]:
    """
    STEP 3: AI analyzes filtered results and generates response.

    Shows transparent reasoning by repeating back what was understood.

    Args:
        user_query: Original user question
        filtered_df: Filtered dataset (result of keyword search)
        original_count: Original dataset size before filtering
        active_filters: Active UI filters (so AI knows context)
        extracted_keywords: Keywords extracted by AI in Step 1 (for transparency)
        thinking_mode: "auto", "quick", "normal", or "deep"
        conversation_history: Previous exchanges for context
        active_ta: Active therapeutic area scope (e.g., "Bladder Cancer")
        latest_report: Latest insights report for the active TA (if available)

    Yields:
        Response tokens for streaming
    """

    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    # Simplified thinking mode: Standard (default) or Deep Thinking
    if thinking_mode == "deep":
        reasoning_effort = "medium"
        verbosity = "medium"
        print(f"[THINKING MODE] Deep Thinking - medium reasoning, medium verbosity")
    else:  # "standard" or default
        reasoning_effort = "low"
        verbosity = "low"
        print(f"[THINKING MODE] Standard - low reasoning, low verbosity")

    # Format filtered data - ALWAYS include abstracts if available (empty DataFrame is fine - AI will handle naturally)
    essential_cols = ['Identifier', 'Title', 'Speakers', 'Speaker Location', 'Affiliation', 'Date', 'Time', 'Session', 'Theme']

    # Check if Abstract column exists in the DataFrame
    if 'Abstract' in filtered_df.columns:
        essential_cols.append('Abstract')
        # Check if abstracts are actually populated (not all NaN)
        non_null_abstracts = filtered_df['Abstract'].notna().sum()
        print(f"[ABSTRACT MODE] Including Abstract column - {non_null_abstracts}/{len(filtered_df)} studies have abstracts")
    else:
        print(f"[NO ABSTRACTS] Abstract column not found in DataFrame")

    available_cols = [col for col in essential_cols if col in filtered_df.columns]
    print(f"[DATA COLUMNS] Sending to AI: {', '.join(available_cols)}")
    dataset_json = filtered_df[available_cols].to_json(orient='records', indent=2) if len(filtered_df) > 0 else "[]"

    # Build interpretation summary for transparency
    interpretation_parts = []
    if extracted_keywords:
        if extracted_keywords.get('dates'):
            interpretation_parts.append(f"on **{', '.join(extracted_keywords['dates'])}**")
        if extracted_keywords.get('drugs'):
            drugs_str = " + ".join(extracted_keywords['drugs'])
            interpretation_parts.append(f"about **{drugs_str}**")
        if extracted_keywords.get('drug_classes'):
            interpretation_parts.append(f"**{', '.join(extracted_keywords['drug_classes'])}**")
        if extracted_keywords.get('therapeutic_areas'):
            interpretation_parts.append(f"in **{', '.join(extracted_keywords['therapeutic_areas'])}**")
        if extracted_keywords.get('institutions'):
            interpretation_parts.append(f"from **{', '.join(extracted_keywords['institutions'])}**")

    interpretation_summary = " ".join(interpretation_parts) if interpretation_parts else "matching your query"

    # Build active filter context for system prompt
    filter_context_parts = []
    if active_filters.get('ta'):
        filter_context_parts.append(f"**Therapeutic Area Filter:** {', '.join(active_filters['ta'])}")
    if active_filters.get('drug'):
        filter_context_parts.append(f"**Drug Filter:** {', '.join(active_filters['drug'])}")
    filter_context_str = "\n".join(filter_context_parts) if filter_context_parts else "No active filters"

    # Build conversation history context
    history_context = ""
    if conversation_history and len(conversation_history) > 0:
        history_context = "\n\n**CONVERSATION HISTORY (for context):**\n"
        for i, exchange in enumerate(conversation_history[-3:], 1):  # Last 3 exchanges for analyzer
            history_context += f"\nExchange {i}:\n"
            history_context += f"User: {exchange.get('user', '')}\n"
            history_context += f"Assistant: {exchange.get('assistant', '')[:150]}...\n"

    # Build report context (if available) - pass entire report
    report_context = ""
    if active_ta and latest_report:
        report_context = f"\n\n**LATEST INSIGHTS REPORT FOR {active_ta.upper()}:**\n(This is the most recent comprehensive analysis generated for this therapeutic area. Use it to provide deeper context and answer follow-up questions.)\n\n{latest_report}\n"

    # Detect query intent from extracted_keywords
    query_intent = extracted_keywords.get('response_type', 'search') if extracted_keywords else 'search'

    # Build system prompt
    system_prompt = f"""You are an AI medical affairs intelligence assistant for EMD Serono (Merck KGaA).

**YOUR SCOPE - PHARMACEUTICAL MEDICAL AFFAIRS ONLY:**
You help with:
- Conference intelligence (ESMO 2025 studies)
- Drug mechanisms, competitive landscapes, clinical data
- Treatment strategies and market dynamics
- Medical/scientific questions about oncology and therapeutics

**CRITICAL - OFF-TOPIC QUERIES:**
If the user asks about topics outside pharmaceutical/medical/scientific scope (cooking, sports, general knowledge, etc.):
- Politely decline: "I'm specialized in pharmaceutical medical affairs and conference intelligence"
- Briefly offer to help with relevant topics instead
- DO NOT answer the off-topic question - redirect to your expertise

**YOUR KNOWLEDGE BASE:**
You have comprehensive pharmaceutical medical knowledge including:
- Drug mechanisms of action (MOAs), targets, and pharmacology
- Treatment landscapes across therapeutic areas
- Standard of care and guideline-directed therapy
- Clinical trial design and endpoints
- Regulatory approvals and label positioning
- Competitive dynamics and market access strategies

**IMPORTANT:** You are NOT just a data retrieval system. The conference studies provided are SUPPORTING EVIDENCE to contextualize your strategic analysis, not your primary knowledge source.

**ACTIVE FILTERS (USER'S VIEW):**
{filter_context_str}

**Important:** The user has these filters active in their UI. They are viewing a FILTERED subset of the conference data based on these selections.

**Company Assets:**
1. Bavencio (avelumab) - PD-L1 inhibitor for bladder cancer
2. Tepmetko (tepotinib) - MET inhibitor for NSCLC with MET alterations
3. Erbitux (cetuximab) - EGFR inhibitor for CRC/H&N

**QUERY INTENT DETECTION:**
Your role changes based on what the user is asking:

**Type 1: RETRIEVAL Queries** ("What studies...", "Show me...", "Find presentations about...")
→ Goal: Describe the filtered studies in detail
→ Response: Start with what studies you found, then analyze them
→ Use study Identifiers, cite abstracts, describe presenters/institutions

**Type 2: CONCEPTUAL Queries** ("What is the difference between X and Y?", "How does X work?", "What's the MOA of X?")
→ Goal: Answer with medical/pharmacological knowledge FIRST
→ Response: Start directly with the answer (mechanisms, definitions, comparisons)
→ Use studies as SUPPORTING EVIDENCE only if provided (e.g., "Based on study 1234P, we see...")
→ If no studies provided, answer purely from medical knowledge
→ DO NOT say "I found N studies" or "The filtered search returned..." - just answer the question

**Type 3: STRATEGIC Queries** ("How could X gain market share?", "What's the competitive landscape?", "Market dynamics...")
→ Goal: Provide strategic analysis using competitive intelligence
→ Response: Strategic insights first, use studies as evidence of trends
→ Frame around EMD assets (avelumab, tepotinib, cetuximab) when relevant
→ Use your pharmaceutical medical knowledge to assess:
  * Treatment sequencing and positioning
  * Unmet needs and market gaps
  * Payer/provider perspectives on value
  * Guideline adoption and KOL influence
  * Competitive differentiation opportunities

**CRITICAL RESPONSE STRUCTURE - 70/30 RULE:**
Your primary job is to ANSWER THE USER'S QUESTION directly and thoughtfully (70% of response).
After answering, mention relevant supporting studies as evidence (30% of response).

❌ WRONG - Table description focus:
"I found 92 studies about this topic. The table shows studies from these institutions..."

✅ RIGHT - Question-first approach:
"[Direct answer to user's question - 2-3 paragraphs]
Supporting evidence: Studies 1234P, 5678P at ESMO show... [cite specific findings]"

For "What is X?" queries:
1. Answer what X is (definition, mechanism, indication) - 70%
2. Then: "By the way, X appears in [N] studies at ESMO 2025:" - 30%
3. Mention 1-3 key studies with brief findings

End responses with: "Would you like me to dive deeper into any of these studies?" (not a menu of options)

**IMPORTANT - Abstract Usage:**
- If the filtered data includes "Abstract" fields, use them to provide evidence-based answers
- When user asks about efficacy, safety, results, methods, or study details, extract specific data points from abstracts:
  * Response rates (ORR, DCR, etc.) with confidence intervals
  * Survival data (PFS, OS) with hazard ratios and p-values
  * Safety data (grade 3-4 AEs, discontinuation rates, specific toxicities)
  * Study design (phase, N, randomization, endpoints)
  * Key takeaways and conclusions
- For "summary of study X" queries, provide comprehensive abstract summary
- For specific questions (e.g., "what were the efficacy results"), focus only on relevant sections
- Always cite the study Identifier when quoting abstract data

**Response Style - NATURAL AND CONVERSATIONAL:**
- NO robotic confirmations like "Confirmed: you want..." or "What I understood..."
- Start DIRECTLY with the answer to their question
- For simple queries (who/when/what): answer directly and concisely
- For evidence queries with abstracts: extract and cite specific data points
- For strategic queries: provide depth and competitive context using EMD assets as reference
- End with ONE specific follow-up suggestion if relevant, not a menu of options
- Infer strategic implications from titles and KOL affiliations even without full abstracts
{history_context}{report_context}"""

    # Build data availability notice
    has_abstracts = 'Abstract' in available_cols
    data_notice = ""
    if has_abstracts:
        data_notice = "\n\n🔬 **IMPORTANT: FULL ABSTRACTS ARE INCLUDED BELOW**\nThe JSON data includes complete 'Abstract' fields for all studies. Extract specific data points (response rates, survival, safety, study design, conclusions) directly from these abstracts. DO NOT say you need to retrieve abstracts - you already have them."
    else:
        data_notice = "\n\n📋 **Data Available:** Study metadata (title, speakers, affiliations, sessions). Full abstracts not included."

    # Build user message - conditional based on query type
    if query_intent == 'conceptual_query':
        # Conceptual query - emphasize conference intelligence when studies found
        if len(filtered_df) > 0:
            user_message = f"""**User Question:** {user_query}

**Conference Intelligence Context:** I found {len(filtered_df)} ESMO 2025 studies related to this topic.
{data_notice}

**CRITICAL RESPONSE STRUCTURE (70/30 RULE):**
1. **ANSWER THE QUESTION FIRST (70%):** Start by answering the user's question directly using your pharmaceutical medical knowledge
   - For "What is X?": Define X, explain mechanism, indication, approval status, competitive position
   - For strategic questions: Provide thoughtful strategic analysis of the competitive landscape
   - For comparison questions: Explain the key differences with clinical context
2. **THEN cite supporting evidence (30%):** After answering, transition naturally to conference data
   - "By the way, X appears in {len(filtered_df)} studies at ESMO 2025:"
   - Mention 1-3 key studies with Identifiers and brief findings from abstracts
   - Provide strategic context if relevant to EMD portfolio
3. **Table display:** Note that a detailed table of all {len(filtered_df)} studies will appear AFTER your response

**Studies Available (JSON format with {len(available_cols)} fields: {', '.join(available_cols)}):**
{dataset_json}

Answer the user's question using BOTH your medical knowledge AND the conference studies above. Always cite study Identifiers when referencing data. End with: "Would you like me to dive deeper into any of these studies?"
"""
        else:
            # No studies - pure knowledge answer
            user_message = f"""**User Question:** {user_query}

Answer the user's question directly using your medical and pharmaceutical knowledge. No conference studies were found for this topic at ESMO 2025."""

    else:
        # Retrieval/search query - show filtering results
        user_message = f"""**Original Query:** {user_query}

**What I Understood:** Studies {interpretation_summary}

**Filtering Results:**
- Started with: {original_count} studies total
- Filtered to: {len(filtered_df)} studies
{data_notice}

**Filtered Studies (JSON format with {len(available_cols)} fields: {', '.join(available_cols)}):**
{dataset_json}

Analyze these {len(filtered_df)} studies and answer the user's question. Cite specific study Identifiers when referencing data."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    try:
        stream = client.responses.create(
            model="gpt-5-mini",
            input=messages,
            reasoning={"effort": reasoning_effort},  # "low" (standard) or "medium" (deep thinking)
            text={"verbosity": verbosity},  # "low" (standard) or "medium" (deep thinking)
            stream=True
        )

        for event in stream:
            if event.type == "response.output_text.delta":
                yield event.delta
            elif event.type == "response.done":
                if hasattr(event, 'response') and hasattr(event.response, 'finish_reason'):
                    print(f"[AI ANALYSIS] Finish reason: {event.response.finish_reason}")

    except Exception as e:
        yield f"\n\nError analyzing results: {str(e)}"
        print(f"[AI ANALYSIS ERROR] {e}")
