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
    Main chat handler - Two-step AI-first approach.

    Step 1: AI interprets query and generates search keywords (with conversation context)
    Step 2: Filter DataFrame using keywords
    Step 3: AI analyzes filtered results (with conversation context + latest report if available)

    Args:
        df: Full conference dataset (already filtered by UI filters)
        user_query: Raw user question
        active_filters: Dict of active UI filters
        conversation_history: List of {user: str, assistant: str} from previous exchanges
        thinking_mode: "auto" (default), "quick", "normal", or "deep"
        active_ta: Active therapeutic area from button click (e.g., "Bladder Cancer")
        latest_report: Latest generated insights report for the active TA (if available)

    Returns:
        {
            'type': 'ai_response',
            'filtered_data': DataFrame (filtered results for table),
            'response_stream': generator (AI analysis tokens)
        }
    """

    if conversation_history is None:
        conversation_history = []

    print(f"\n{'='*70}")
    print(f"[AI-FIRST] User query: {user_query}")
    print(f"[AI-FIRST] Starting dataset: {len(df)} studies")
    print(f"[AI-FIRST] Conversation history: {len(conversation_history)} previous exchanges")
    print(f"{'='*70}")

    # STEP 1: AI interprets query and decides response strategy
    print(f"\n[STEP 1] AI interpreting query...")
    interpretation = extract_search_keywords_from_ai(user_query, len(df), active_filters, conversation_history)

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

    # Handle conceptual/strategic query (answer with knowledge, optionally use studies as evidence)
    if response_type == 'conceptual_query':
        print(f"[STEP 1] AI detected conceptual/strategic query")
        topic = interpretation.get('topic', '')
        context_entities = interpretation.get('context_entities', [])
        retrieve_studies = interpretation.get('retrieve_supporting_studies', False)
        print(f"[CONCEPTUAL] Topic: {topic}")
        print(f"[CONCEPTUAL] Context entities: {', '.join(context_entities)}")
        print(f"[CONCEPTUAL] Retrieve supporting studies: {retrieve_studies}")

        # If AI wants supporting studies, filter by context entities
        if retrieve_studies and context_entities:
            print(f"[STEP 2] Filtering for supporting studies about: {', '.join(context_entities)}")
            entity_pattern = '|'.join([re.escape(e) for e in context_entities])
            filtered_df = df[
                df['Title'].str.contains(entity_pattern, case=False, na=False, regex=True)
            ]
            print(f"[STEP 2] Filtered: {len(df)} -> {len(filtered_df)} supporting studies")
        else:
            # No study filtering needed - AI will answer from knowledge
            filtered_df = pd.DataFrame()
            print(f"[STEP 2] No study filtering needed - conceptual answer from medical knowledge")

        # Skip to Step 3 - AI answers conceptually
        print(f"\n[STEP 3] AI answering conceptual query about '{topic}'...")
        response_generator = analyze_filtered_results_with_ai(
            user_query=user_query,
            filtered_df=filtered_df,
            original_count=len(df),
            active_filters=active_filters,
            extracted_keywords={'response_type': 'conceptual_query', 'topic': topic, 'context_entities': context_entities},
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

    # Handle follow-up question (reuse previous data from conversation history)
    if response_type == 'followup':
        print(f"[STEP 1] AI detected follow-up question - extracting previous study identifiers from conversation history")
        context_query = interpretation.get('context_query', '')
        print(f"[FOLLOWUP] Context: {context_query}")

        # Extract study identifiers mentioned in the most recent assistant response
        if conversation_history:
            last_response = conversation_history[-1].get('assistant', '')
            # Find all study identifiers (pattern: digits followed by P, like "1234P")
            import re
            identifier_pattern = r'\b(\d+P)\b'
            identifiers = list(set(re.findall(identifier_pattern, last_response)))

            if identifiers:
                print(f"[FOLLOWUP] Found {len(identifiers)} study identifiers in previous response: {', '.join(identifiers[:10])}")
                # Filter DataFrame to only include these studies
                filtered_df = df[df['Identifier'].isin(identifiers)].copy()
                print(f"[FOLLOWUP] Filtered to {len(filtered_df)} studies from previous conversation")

                # Create pseudo-keywords for the analyzer to understand context
                keywords = {
                    'response_type': 'followup',
                    'context_query': context_query,
                    'reused_identifiers': identifiers
                }

                # Skip to Step 3 - AI analyzes the same filtered results
                print(f"\n[STEP 3] AI analyzing {len(filtered_df)} studies from follow-up...")
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
            else:
                print(f"[FOLLOWUP] No study identifiers found in previous response - falling back to full dataset")
                # Fall through to normal search if no identifiers found

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
        active_filters=active_filters,  # Pass active filters so analyzer knows what's filtered
        extracted_keywords=keywords,  # Pass keywords for transparency
        thinking_mode=thinking_mode,  # Pass thinking mode to analyzer
        conversation_history=conversation_history,  # Pass history for context
        active_ta=active_ta,  # Pass active TA scope
        latest_report=latest_report  # Pass latest generated report for context
    )

    return {
        'type': 'ai_response',
        'filtered_data': filtered_df,
        'response_stream': response_generator
    }


def extract_search_keywords_from_ai(
    user_query: str,
    dataset_size: int,
    active_filters: Dict,
    conversation_history: List[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    STEP 1: AI interprets query and decides response strategy.

    The AI determines:
    1. Is this a greeting/casual query? → Return direct response
    2. Is this a data query? → Extract search keywords
    3. Is this a follow-up question? → Use conversation context

    Args:
        user_query: User's raw question
        dataset_size: Number of studies currently visible
        active_filters: Active UI filters for context
        conversation_history: Previous user/assistant exchanges for context

    Returns:
        Dict with either:
        - {"response_type": "greeting", "message": "Hi! I can help..."} for casual queries
        - {"response_type": "search", "drugs": [...], "dates": [...], ...} for data queries
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

    # Build conversation context - FULL history for follow-up detection
    history_context = ""
    if conversation_history:
        history_context = "\n\n**CONVERSATION HISTORY (FULL - last 5 exchanges):**\n"
        for i, exchange in enumerate(conversation_history[-5:], 1):  # Last 5 exchanges
            history_context += f"\n--- Exchange {i} ---\n"
            history_context += f"User: {exchange.get('user', '')}\n"
            # Include FULL assistant response (no truncation) for follow-up detection
            history_context += f"Assistant: {exchange.get('assistant', '')}\n"

    system_prompt = f"""You are a pharmaceutical query interpreter for a conference intelligence system.

**CONTEXT:**
- User is viewing {dataset_size} studies{filter_context} from ESMO 2025
- The dataset is already pre-filtered by UI filters (if any)
- Your job: Extract ONLY the minimal keyword set needed to retrieve what the user asked for

**Option 1 - Casual/Greeting Query** (Hi, Hello, Thanks, How are you, etc.):
Return: {{"response_type": "greeting", "message": "your friendly conversational response"}}
- Acknowledge the greeting naturally
- Mention the {dataset_size} studies{filter_context} they're viewing
- Offer to help: "What would you like to know?"

**Option 2 - Follow-Up Question** (referring to previous studies/data):
CRITICAL: If the user's query refers to previous results using phrases like:
- "these studies", "those presentations", "the above data", "from that list"
- "tell me more about them", "what do they mean", "how do they impact..."
- Any question that clearly builds on the previous exchange
Then return: {{"response_type": "followup", "context_query": "brief summary of what user is asking about the previous data"}}
IMPORTANT: The system will reuse the previously filtered data - DO NOT extract new search keywords.

**Option 3 - Conceptual/Strategic Question** (answering with medical/strategic knowledge):
CRITICAL: If the user asks a question that requires EXPLANATION, COMPARISON, or STRATEGIC ANALYSIS rather than study retrieval:
- Mechanism questions: "What is the difference between X and Y?", "How does X work?", "What's the MOA of X?"
- Market/strategy questions: "How could X gain market share?", "What's the competitive landscape for X?"
- Background questions: "Tell me about X", "What is X used for?"
Then return: {{"response_type": "conceptual_query", "topic": "brief description of what they're asking about", "context_entities": ["entity1", "entity2"], "retrieve_supporting_studies": true/false}}
- Set "retrieve_supporting_studies" to TRUE if studies would add value (e.g., "How could retifanlimab compete?" → get retifanlimab studies)
- Set to FALSE if it's pure knowledge question (e.g., "What's the difference between PD-1 and PD-L1?")

**Option 4 - New Data Query** - Apply DECISION PRIORITY:

**DECISION PRIORITY (CRITICAL):**
1) If user mentions a MOLECULAR ENTITY (mutation/alteration/pathway/biomarker), that becomes the PRIMARY filter
   - Examples: "METex14", "MET exon 14 skipping", "EGFR L858R", "HER2-low", "PD-L1 ≥50%", "KRAS G12C"
   - When molecular entity is present, DO NOT infer or add drug filters unless user explicitly asks for drugs
   - Put molecular entities in search_terms, NOT drug_classes

2) If user mentions DRUG ABBREVIATIONS, expand them to full names:
   - "EV" → enfortumab vedotin
   - "P" / "pembro" → pembrolizumab
   - "Nivo" → nivolumab
   - "Atezo" → atezolizumab
   - For combinations (like "EV + P"), provide BOTH drug names

3) Only extract DRUGS if:
   - User explicitly mentions them (name or abbreviation), OR
   - User asks for drug comparisons

4) Prefer RECALL over PRECISION on first pass
   - Be conservative with constraints
   - Don't add filters the user didn't ask for
   - User can refine later if needed

5) Do NOT extract therapeutic_areas or drug_classes that are already in active filters above

**Output Format:**
Return: {{"response_type": "search", "drugs": [...], "drug_classes": [...], "therapeutic_areas": [...], "institutions": [...], "dates": [...], "speakers": [...], "search_terms": [...]}}

Return ONLY valid JSON, no other text."""

    # Combine system and user prompts into single input string for Responses API
    combined_prompt = f"""{system_prompt}{history_context}

USER QUERY: "{user_query}"

**Examples demonstrating DECISION PRIORITY:**

Greeting:
"Hello!" → {{"response_type": "greeting", "message": "Hi! I can help you explore the {dataset_size} studies{filter_context}. What would you like to know?"}}

Follow-up (referring to previous studies):
"What do these studies mean for avelumab?" → {{"response_type": "followup", "context_query": "Impact of previously discussed studies on avelumab positioning"}}
"Tell me more about them" → {{"response_type": "followup", "context_query": "Additional details about previously mentioned studies"}}

Conceptual/Knowledge Questions (answer with medical knowledge, optionally use studies as evidence):
"What is the difference between PD-1 and PD-L1 inhibitors?" → {{"response_type": "conceptual_query", "topic": "Mechanism difference between PD-1 vs PD-L1 checkpoint inhibitors", "context_entities": [], "retrieve_supporting_studies": false}}
"How could retifanlimab gain market share in MCC?" → {{"response_type": "conceptual_query", "topic": "Market positioning strategy for retifanlimab in Merkel cell carcinoma", "context_entities": ["retifanlimab", "avelumab"], "retrieve_supporting_studies": true}}
"Tell me about tepotinib's mechanism of action" → {{"response_type": "conceptual_query", "topic": "Tepotinib MET inhibitor mechanism", "context_entities": ["tepotinib"], "retrieve_supporting_studies": false}}

Drug abbreviation expansion (NEW search):
"EV + P studies" → {{"response_type": "search", "drugs": ["enfortumab vedotin", "pembrolizumab"], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": [], "speakers": [], "search_terms": []}}

Molecular entity (PRIMARY filter - don't add drugs):
"METex14 skipping studies" → {{"response_type": "search", "drugs": [], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": [], "speakers": [], "search_terms": ["METex14", "MET exon 14 skipping", "MET exon14 skipping"]}}

Molecular entity + explicit drug:
"capmatinib in METex14" → {{"response_type": "search", "drugs": ["capmatinib"], "drug_classes": [], "therapeutic_areas": [], "institutions": [], "dates": [], "speakers": [], "search_terms": ["METex14", "MET exon 14"]}}

Drug class (only when explicitly asked):
"ADC studies in breast cancer" → {{"response_type": "search", "drugs": [], "drug_classes": ["antibody-drug conjugate", "ADC"], "therapeutic_areas": ["breast cancer"], "institutions": [], "dates": [], "speakers": [], "search_terms": []}}

Now interpret the user query above. Return ONLY valid JSON."""

    try:
        # Use Responses API (input is a string, not messages array)
        print(f"[AI EXTRACTION] Calling GPT-5 API...")
        response = client.responses.create(
            model="gpt-5-mini",
            input=combined_prompt,  # Single string, not array of messages
            reasoning={"effort": "medium"},  # MEDIUM: Balanced - keyword extraction doesn't need high reasoning
            text={"verbosity": "low"},  # LOW: Output is just JSON keywords
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

    # Format filtered data - ALWAYS include abstracts if available
    essential_cols = ['Identifier', 'Title', 'Speakers', 'Affiliation', 'Date', 'Time', 'Session', 'Theme']

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
        # Conceptual query - minimal framing, let AI answer naturally
        if len(filtered_df) > 0:
            user_message = f"""**User Question:** {user_query}

**Supporting Context:** {len(filtered_df)} related studies are available as supporting evidence (if relevant to your answer).
{data_notice}

**Studies Available (JSON format with {len(available_cols)} fields: {', '.join(available_cols)}):**
{dataset_json}

Answer the user's question directly using your medical knowledge. Use the studies above as supporting evidence only if they add value."""
        else:
            # No studies - pure knowledge answer
            user_message = f"""**User Question:** {user_query}

Answer the user's question directly using your medical and pharmaceutical knowledge. No conference studies were filtered for this conceptual question."""

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
