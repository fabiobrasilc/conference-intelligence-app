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
    active_filters: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    Main chat handler - Two-step AI-first approach.

    Step 1: AI interprets query and generates search keywords
    Step 2: Filter DataFrame using keywords
    Step 3: AI analyzes filtered results

    Args:
        df: Full conference dataset (already filtered by UI filters)
        user_query: Raw user question
        active_filters: Dict of active UI filters

    Returns:
        {
            'type': 'ai_response',
            'filtered_data': DataFrame (filtered results for table),
            'response_stream': generator (AI analysis tokens)
        }
    """

    print(f"\n{'='*70}")
    print(f"[AI-FIRST] User query: {user_query}")
    print(f"[AI-FIRST] Starting dataset: {len(df)} studies")
    print(f"{'='*70}")

    # STEP 1: AI interprets query and generates search keywords
    print(f"\n[STEP 1] AI interpreting query and generating keywords...")
    keywords = extract_search_keywords_from_ai(user_query)

    print(f"[STEP 1] AI-generated keywords:")
    for key, values in keywords.items():
        if values:
            print(f"  {key}: {values}")

    # STEP 2: Filter DataFrame using AI-generated keywords
    print(f"\n[STEP 2] Filtering dataset with AI-generated keywords...")
    filtered_df = filter_dataframe_with_keywords(df, keywords)
    print(f"[STEP 2] Filtered: {len(df)} -> {len(filtered_df)} studies")

    if len(filtered_df) > 0 and len(filtered_df) <= 50:
        sample_ids = filtered_df['Identifier'].dropna().head(10).tolist()
        if sample_ids:
            print(f"[STEP 2] Sample IDs: {', '.join(map(str, sample_ids))}")

    # STEP 3: AI analyzes filtered results
    print(f"\n[STEP 3] AI analyzing {len(filtered_df)} filtered studies...")
    response_generator = analyze_filtered_results_with_ai(
        user_query=user_query,
        filtered_df=filtered_df,
        original_count=len(df),
        filters=active_filters,
        extracted_keywords=keywords  # Pass keywords for transparency
    )

    return {
        'type': 'ai_response',
        'filtered_data': filtered_df,
        'response_stream': response_generator
    }


def extract_search_keywords_from_ai(user_query: str) -> Dict[str, List[str]]:
    """
    STEP 1: AI interprets query and generates search keywords.

    The AI uses its pharmaceutical knowledge to:
    - Understand abbreviations (EV = enfortumab vedotin)
    - Identify drug classes (ADC = antibody-drug conjugates)
    - Extract dates, institutions, therapeutic areas, etc.

    Args:
        user_query: User's raw question

    Returns:
        Dict with search keywords:
        {
            'drugs': ['enfortumab vedotin', 'pembrolizumab'],
            'drug_classes': ['ADC'],
            'therapeutic_areas': ['bladder cancer', 'urothelial'],
            'institutions': ['MD Anderson'],
            'dates': ['10/19'],
            'search_terms': ['combination']  # other relevant terms
        }
    """

    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    system_prompt = """You are a pharmaceutical keyword extraction expert.

Your task: Extract search keywords from user queries for filtering a medical conference database.

**Your pharmaceutical knowledge:**
- Drug abbreviations: "EV" = enfortumab vedotin, "P" = pembrolizumab, "Nivo" = nivolumab
- Drug classes: "ADC" = antibody-drug conjugates, "ICI" = immune checkpoint inhibitors, "TKI" = tyrosine kinase inhibitors
- For combination queries (like "EV + P"), provide BOTH drug names
- Be specific with full generic names

**Output Format:**
Return ONLY valid JSON with this exact structure (no other text):
{
    "drugs": ["list of specific drug names"],
    "drug_classes": ["list of drug classes like ADC, ICI, TKI"],
    "therapeutic_areas": ["list of cancer types or disease areas"],
    "institutions": ["list of specific institutions or hospitals"],
    "dates": ["list of dates in MM/DD format"],
    "speakers": ["list of speaker/author names"],
    "search_terms": ["other relevant keywords"]
}"""

    user_prompt = f"""Extract keywords from this query: "{user_query}"

Examples for reference:

Query: "EV + P data updates"
{{"drugs": ["enfortumab vedotin", "pembrolizumab"], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": [], "speakers": [], "search_terms": ["combination"]}}

Query: "Show me ADC studies in breast cancer"
{{"drugs": [], "drug_classes": ["antibody-drug conjugate", "ADC"], "therapeutic_areas": ["breast cancer"], "institutions": [], "dates": [], "speakers": [], "search_terms": []}}

Query: "What's MD Anderson presenting on 10/19?"
{{"drugs": [], "drug_classes": [], "therapeutic_areas": [], "institutions": ["MD Anderson", "MD Anderson Cancer Center"], "dates": ["10/19"], "speakers": [], "search_terms": []}}

Now extract keywords for the user query. Return ONLY valid JSON."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=messages,
            reasoning={"effort": "high"},
            text={"verbosity": "low"},  # We just want JSON output
            max_output_tokens=1000,
            stream=True
        )

        # Extract the JSON response
        response_text = ""
        event_count = 0
        for event in response:
            event_count += 1
            if event.type == "response.output_text.delta":
                response_text += event.delta
            elif event.type == "response.done":
                print(f"[AI EXTRACTION] Stream done after {event_count} events")
                break
            elif event.type == "response.incomplete":
                print(f"[AI EXTRACTION WARNING] Stream incomplete after {event_count} events - may indicate API issue")
                # Continue anyway, might have partial data

        print(f"[AI EXTRACTION] Extracted {len(response_text)} chars from {event_count} events")

        # Parse JSON
        keywords = json.loads(response_text.strip())

        return keywords

    except Exception as e:
        print(f"[AI EXTRACTION ERROR] {e}")
        import traceback
        traceback.print_exc()
        # Fallback: return empty keywords
        return {
            'drugs': [],
            'drug_classes': [],
            'therapeutic_areas': [],
            'institutions': [],
            'dates': [],
            'speakers': [],
            'search_terms': []
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
    if keywords.get('dates'):
        date_pattern = '|'.join([re.escape(d) for d in keywords['dates']])
        filtered = filtered[
            filtered['Date'].str.contains(date_pattern, case=False, na=False, regex=True)
        ]
        print(f"  After date filter: {len(filtered)} studies")

    # 2. Filter by institutions (if specified)
    if keywords.get('institutions'):
        inst_pattern = '|'.join([re.escape(inst) for inst in keywords['institutions']])
        filtered = filtered[
            filtered['Affiliation'].str.contains(inst_pattern, case=False, na=False, regex=True)
        ]
        print(f"  After institution filter: {len(filtered)} studies")

    # 3. Filter by drugs (if specified)
    if keywords.get('drugs'):
        # For combination queries, we need BOTH drugs present
        if len(keywords['drugs']) > 1:
            # Combination: ALL drugs must be present
            for drug in keywords['drugs']:
                drug_pattern = re.escape(drug)
                if 'search_text_normalized' in filtered.columns:
                    filtered = filtered[
                        filtered['search_text_normalized'].str.contains(
                            drug_pattern, case=False, na=False, regex=True
                        )
                    ]
                else:
                    filtered = filtered[
                        filtered['Title'].str.contains(drug_pattern, case=False, na=False, regex=True)
                    ]
                print(f"  After '{drug}' filter: {len(filtered)} studies")
        else:
            # Single drug: OR search
            drug_pattern = '|'.join([re.escape(d) for d in keywords['drugs']])
            if 'search_text_normalized' in filtered.columns:
                filtered = filtered[
                    filtered['search_text_normalized'].str.contains(
                        drug_pattern, case=False, na=False, regex=True
                    )
                ]
            else:
                filtered = filtered[
                    filtered['Title'].str.contains(drug_pattern, case=False, na=False, regex=True)
                ]
            print(f"  After drug filter: {len(filtered)} studies")

    # 4. Filter by drug classes (if specified and no specific drugs)
    if keywords.get('drug_classes') and not keywords.get('drugs'):
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

    # 6. Filter by speakers (if specified)
    if keywords.get('speakers'):
        speaker_pattern = '|'.join([re.escape(s) for s in keywords['speakers']])
        filtered = filtered[
            filtered['Speakers'].str.contains(speaker_pattern, case=False, na=False, regex=True)
        ]
        print(f"  After speaker filter: {len(filtered)} studies")

    # 7. Filter by additional search terms (if specified)
    # NOTE: Only apply if we don't already have drug-based filtering
    # This prevents over-filtering when drugs already imply the context
    if keywords.get('search_terms') and not keywords.get('drugs'):
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
    filters: Dict[str, List[str]],
    extracted_keywords: Dict[str, List[str]] = None
) -> Generator[str, None, None]:
    """
    STEP 3: AI analyzes filtered results and generates response.

    Shows transparent reasoning by repeating back what was understood.

    Args:
        user_query: Original user question
        filtered_df: Filtered dataset (result of keyword search)
        original_count: Original dataset size before filtering
        filters: Active UI filters
        extracted_keywords: Keywords extracted by AI in Step 1 (for transparency)

    Yields:
        Response tokens for streaming
    """

    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    # Format filtered data
    essential_cols = ['Identifier', 'Title', 'Speakers', 'Affiliation', 'Date', 'Time', 'Session', 'Theme']
    available_cols = [col for col in essential_cols if col in filtered_df.columns]

    dataset_json = filtered_df[available_cols].to_json(orient='records', indent=2)

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

    # Build system prompt
    system_prompt = """You are an AI medical affairs intelligence assistant for EMD Serono (Merck KGaA).

**Company Assets:**
1. Bavencio (avelumab) - PD-L1 inhibitor for bladder cancer
2. Tepmetko (tepotinib) - MET inhibitor for NSCLC
3. Erbitux (cetuximab) - EGFR inhibitor for CRC/H&N

**Response Structure (CRITICAL):**
1. START by confirming what you understood in a natural way
   Example: "I found 6 studies on **10/18** about **nivolumab** in **renal cell carcinoma**."
   Or: "I found 11 studies about the **enfortumab vedotin + pembrolizumab** combination."
2. THEN provide your analysis

**Guidelines:**
- You are receiving FILTERED data (these specific studies matched the user's intent)
- Always cite study Identifiers when referencing presentations
- Be concise but informative
- If results seem surprisingly small/large, acknowledge it"""

    user_message = f"""**Original Query:** {user_query}

**What I Understood:** Studies {interpretation_summary}

**Filtering Results:**
- Started with: {original_count} studies total
- Filtered to: {len(filtered_df)} studies

**Filtered Studies:**
{dataset_json}

Please analyze these {len(filtered_df)} studies. Start by confirming what you understood, then provide analysis citing specific Identifiers."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    try:
        stream = client.responses.create(
            model="gpt-5-mini",
            input=messages,
            reasoning={"effort": "medium"},
            text={"verbosity": "medium"},
            max_output_tokens=4000,
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
