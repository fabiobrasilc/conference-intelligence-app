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

    # STEP 1: AI interprets query and decides response strategy
    print(f"\n[STEP 1] AI interpreting query...")
    interpretation = extract_search_keywords_from_ai(user_query, len(df), active_filters)

    # Check response type
    response_type = interpretation.get('response_type')

    # Handle greeting
    if response_type == 'greeting':
        print(f"[STEP 1] AI detected greeting - responding conversationally")
        greeting_message = interpretation.get('message', 'How can I help you today?')

        def greeting_generator():
            yield greeting_message

        return {
            'type': 'ai_response',
            'filtered_data': pd.DataFrame(),
            'response_stream': greeting_generator()
        }

    # Handle error
    if response_type == 'error':
        print(f"[STEP 1] AI extraction error - returning error message")
        error_message = interpretation.get('message', 'Sorry, I encountered an error. Please try again.')

        def error_generator():
            yield error_message

        return {
            'type': 'ai_response',
            'filtered_data': pd.DataFrame(),
            'response_stream': error_generator()
        }

    # Data query - extract keywords from interpretation
    keywords = interpretation
    print(f"[STEP 1] AI-generated keywords:")
    for key, values in keywords.items():
        if values and key != 'response_type':
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


def extract_search_keywords_from_ai(user_query: str, dataset_size: int, active_filters: Dict) -> Dict[str, Any]:
    """
    STEP 1: AI interprets query and decides response strategy.

    The AI determines:
    1. Is this a greeting/casual query? → Return direct response
    2. Is this a data query? → Extract search keywords

    Args:
        user_query: User's raw question
        dataset_size: Number of studies currently visible
        active_filters: Active UI filters for context

    Returns:
        Dict with either:
        - {"response_type": "greeting", "message": "Hi! I can help..."} for casual queries
        - {"response_type": "search", "drugs": [...], "dates": [...], ...} for data queries
    """

    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    # Build filter context
    filter_parts = []
    if active_filters.get('ta'):
        filter_parts.append(f"{', '.join(active_filters['ta'])}")
    if active_filters.get('drug'):
        filter_parts.append(f"{', '.join(active_filters['drug'])}")
    filter_context = " about " + " and ".join(filter_parts) if filter_parts else ""

    system_prompt = f"""You are a pharmaceutical query interpreter for a conference intelligence system.

**Context:** User is viewing {dataset_size} studies{filter_context} from ESMO 2025.

**Your task:** Interpret the user's intent and provide appropriate response.

**Option 1 - Casual/Greeting Query** (Hi, Hello, Thanks, How are you, etc.):
Return: {{"response_type": "greeting", "message": "your friendly conversational response"}}
- Acknowledge the greeting naturally
- Mention the {dataset_size} studies{filter_context} they're viewing
- Offer to help: "What would you like to know?"

**Option 2 - Data Query** (asking about studies, drugs, therapeutic areas, etc.):
Return: {{"response_type": "search", "drugs": [...], "drug_classes": [...], "therapeutic_areas": [...], "institutions": [...], "dates": [...], "speakers": [...], "search_terms": [...]}}
- Use your pharmaceutical knowledge to extract keywords
- Drug abbreviations: "EV" = enfortumab vedotin, "P" = pembrolizumab, "Nivo" = nivolumab
- Drug classes: "ADC" = antibody-drug conjugates, "ICI" = immune checkpoint inhibitors
- For combinations (like "EV + P"), provide BOTH drug names
- **IMPORTANT**: Do NOT extract therapeutic_areas, drug_classes, or search_terms that are already in the active filters above - the dataset is already filtered by those
- Focus on extracting NEW information from the query (drugs, dates, institutions, speakers)

Return ONLY valid JSON, no other text."""

    # Combine system and user prompts into single input string for Responses API
    combined_prompt = f"""{system_prompt}

USER QUERY: "{user_query}"

Examples:

"Hello!" → {{"response_type": "greeting", "message": "Hi! I can help you explore the {dataset_size} studies{filter_context}. What would you like to know?"}}

"Thanks!" → {{"response_type": "greeting", "message": "You're welcome! Let me know if you need anything else."}}

"EV + P studies" → {{"response_type": "search", "drugs": ["enfortumab vedotin", "pembrolizumab"], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": [], "speakers": [], "search_terms": []}}

"ADC data in breast cancer" → {{"response_type": "search", "drugs": [], "drug_classes": ["antibody-drug conjugate", "ADC"], "therapeutic_areas": ["breast cancer"], "institutions": [], "dates": [], "speakers": [], "search_terms": []}}

Now interpret the user query above. Return ONLY valid JSON."""

    try:
        # Use Responses API (input is a string, not messages array)
        print(f"[AI EXTRACTION] Calling GPT-5 API...")
        response = client.responses.create(
            model="gpt-5-mini",
            input=combined_prompt,  # Single string, not array of messages
            reasoning={"effort": "low"},  # Use low for simple keyword extraction
            text={"verbosity": "low"},
            max_output_tokens=1000
        )

        # Check response status and error
        print(f"[AI EXTRACTION] Response status: {response.status}")
        print(f"[AI EXTRACTION] Response error: {response.error}")
        print(f"[AI EXTRACTION] Response incomplete_details: {response.incomplete_details}")

        # Check output structure
        if hasattr(response, 'output'):
            print(f"[AI EXTRACTION] Output object: {response.output}")
            if response.output:
                print(f"[AI EXTRACTION] Output type: {type(response.output)}")
                print(f"[AI EXTRACTION] Output dir: {dir(response.output)}")

        # Get response text directly (non-streaming)
        response_text = response.output_text if hasattr(response, 'output_text') else ""
        print(f"[AI EXTRACTION] output_text length: {len(response_text)} chars")

        if response_text:
            print(f"[AI EXTRACTION] output_text preview: {response_text[:200]}")

        # Check if we got empty response
        if not response_text.strip():
            print(f"[AI EXTRACTION ERROR] API returned empty response - retrying with simpler prompt")
            # Return error indicator
            return {
                'response_type': 'error',
                'message': 'Sorry, I had trouble understanding your query. Could you try rephrasing it? For example: "Show me EV + P studies" or "What studies are about pembrolizumab?"'
            }

        # Parse JSON
        keywords = json.loads(response_text.strip())

        return keywords

    except json.JSONDecodeError as e:
        print(f"[AI EXTRACTION ERROR] Invalid JSON from API: {e}")
        print(f"[AI EXTRACTION ERROR] Response text was: {response_text[:200]}")
        return {
            'response_type': 'error',
            'message': 'Sorry, I had trouble processing your request. Could you try rephrasing your question more simply?'
        }
    except Exception as e:
        print(f"[AI EXTRACTION ERROR] {e}")
        import traceback
        traceback.print_exc()
        return {
            'response_type': 'error',
            'message': 'Sorry, I encountered an error. Please try again.'
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
1. If the original query is a casual greeting (Hi, Hello, Thanks, etc.):
   - Respond conversationally
   - Mention the number of studies available and what therapeutic area they cover
   - Offer to help: "What would you like to know?"
   - DO NOT analyze all the studies

2. If the original query is a data question:
   - START by confirming what you understood
     Example: "I found 6 studies on **10/18** about **nivolumab** in **renal cell carcinoma**."
   - THEN provide your analysis

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
