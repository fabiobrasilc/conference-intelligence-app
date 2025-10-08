"""
AI-First Chat Assistant for Conference Intelligence
====================================================

Philosophy: LET THE AI BE THE INTELLIGENCE
- AI handles drug knowledge, understanding, classification via GPT-5 training
- We provide: data grounding, UI filters, basic search
- NO hardcoded drug expansion, intent classification, or rigid rules

Functions:
- handle_chat_query() - Main entry point
- basic_search() - Optional text search to narrow dataset
- prepare_ai_context() - Format data for GPT-5 prompt with system instructions
- stream_ai_response() - GPT-5 streaming
"""

import pandas as pd
from typing import Dict, List, Any, Generator
import re
from openai import OpenAI
import os


def handle_chat_query(
    df: pd.DataFrame,
    user_query: str,
    active_filters: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    Main chat handler - AI-first approach.

    Args:
        df: Full conference dataset (already filtered by UI filters)
        user_query: Raw user question
        active_filters: Dict of active UI filters {drug: [], ta: [], session: [], date: []}

    Returns:
        {
            'type': 'ai_response',
            'filtered_data': DataFrame (for potential table display),
            'response_stream': generator (GPT-5 tokens)
        }
    """

    print(f"[AI ASSISTANT] Query: {user_query}")
    print(f"[AI ASSISTANT] Dataset size: {len(df)} studies")

    # Step 1: Basic search (optional narrowing for token efficiency)
    # This is NOT filtering - just reducing dataset if obvious keywords present
    relevant_df = basic_search(df, user_query)
    print(f"[AI ASSISTANT] Narrowed to {len(relevant_df)} studies for AI context")

    # Step 2: Prepare context for GPT-5
    ai_messages = prepare_ai_context(
        user_query=user_query,
        dataset=relevant_df,
        filters=active_filters
    )

    # Step 3: Stream GPT-5 response
    response_generator = stream_ai_response(ai_messages)

    return {
        'type': 'ai_response',
        'filtered_data': relevant_df,  # Frontend will display as table if AI indicates
        'response_stream': response_generator
    }


def basic_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """
    Basic text search to narrow dataset for token efficiency.

    Strategy:
    - Extract obvious keywords from query
    - Search in search_text_normalized column (precomputed)
    - Be BROAD - don't over-filter, let AI do fine-grained filtering
    - If no clear keywords → return full dataset (AI handles it)

    Args:
        df: Dataset with search_text_normalized column
        query: User's raw query string

    Returns:
        Filtered DataFrame (or full df if no obvious search terms)
    """

    # Extract search terms (simple approach)
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'show', 'me', 'tell', 'about', 'what', 'are', 'is', 'give', 'all',
        'sessions', 'studies', 'presentations', 'data', 'can', 'you', 'please'
    }

    words = query.lower().split()
    search_terms = [w for w in words if w not in stop_words and len(w) > 2]

    if not search_terms:
        # No obvious search terms - return full dataset
        print("[AI ASSISTANT] No search terms extracted, using full dataset")
        return df

    # Build search pattern (broad OR search across all terms)
    pattern = '|'.join([re.escape(term) for term in search_terms])

    # Search in normalized text column
    if 'search_text_normalized' in df.columns:
        mask = df['search_text_normalized'].str.contains(
            pattern, case=False, na=False, regex=True
        )
        results = df[mask]
    else:
        # Fallback if column doesn't exist
        print("[AI ASSISTANT] Warning: search_text_normalized column missing")
        return df

    # Safety: if too restrictive (< 10 results), return full dataset
    # Let AI handle the filtering rather than risk missing relevant data
    if len(results) < 10 and len(df) > 10:
        print("[AI ASSISTANT] Search too restrictive, using full dataset")
        return df

    return results


def prepare_ai_context(
    user_query: str,
    dataset: pd.DataFrame,
    filters: Dict[str, List[str]]
) -> List[Dict[str, str]]:
    """
    Create complete context prompt for GPT-5.

    Includes:
    - System prompt with role, company context, instructions (from The Bible)
    - User query
    - Active filters
    - Dataset (JSON format)

    Returns:
        List of message dicts for OpenAI chat API
    """

    # Format active filters for context
    filter_text = []
    if filters.get('ta'):
        filter_text.append(f"Therapeutic Areas: {', '.join(filters['ta'])}")
    if filters.get('drug'):
        filter_text.append(f"Drugs: {', '.join(filters['drug'])}")
    if filters.get('date'):
        filter_text.append(f"Dates: {', '.join(filters['date'])}")
    if filters.get('session'):
        filter_text.append(f"Session Types: {', '.join(filters['session'])}")
    filter_context = "\n".join(filter_text) if filter_text else "No UI filters active"

    # Prepare dataset for AI (limit to essential columns and manageable size)
    essential_cols = ['Identifier', 'Title', 'Speakers', 'Affiliation', 'Date', 'Time', 'Session', 'Theme']
    available_cols = [col for col in essential_cols if col in dataset.columns]

    # Token management: Limit to 500 studies max for context
    dataset_subset = dataset[available_cols].head(500) if len(dataset) > 500 else dataset[available_cols]
    dataset_json = dataset_subset.to_json(orient='records', indent=2)

    # System prompt (from The Bible - ARCHITECTURE_PLAN.md)
    system_prompt = """You are an AI medical affairs intelligence assistant for EMD Serono (Merck KGaA).

**YOUR COMPANY CONTEXT:**
- Company: EMD Serono (Merck KGaA), partnership with Pfizer in oncology
- Parent company: Merck KGaA (Germany)

**Key Assets:**
1. **Bavencio (avelumab)** - PD-L1 checkpoint inhibitor
   - Primary indication: First-line maintenance metastatic urothelial carcinoma (bladder cancer)
   - Also approved: Merkel cell carcinoma, renal cell carcinoma

2. **Tepmetko (tepotinib)** - MET inhibitor
   - Indication: METex14 skipping NSCLC (non-small cell lung cancer)

3. **Erbitux (cetuximab)** - EGFR inhibitor (marketed by Merck KGaA outside US/Canada)
   - Indications: Metastatic colorectal cancer (mCRC), locally advanced/metastatic head & neck cancer

**Your purpose:** Analyze ESMO 2025 for competitive intelligence, KOL engagement, emerging science relevant to these assets and pipeline

**CONFERENCE DATA:**
- 4,686 ESMO 2025 studies/presentations total
- Columns: Title, Speakers, Affiliation, Identifier, Date, Time, Session, Theme
- **Important:** Full abstracts NOT yet available (release Oct 13, 2025)
- Current data: Titles, authors, institutions, session metadata only

**YOUR PHARMACEUTICAL KNOWLEDGE:**
You have extensive training on drug nomenclature - USE IT!
- You know drug abbreviations: "EV" = enfortumab vedotin, "P" = pembrolizumab
- You understand drug classes: "ADC" = antibody-drug conjugates, "ICI" = immune checkpoint inhibitors
- You can infer from naming patterns: "-mab" = antibody, "-tinib" = kinase inhibitor, "-tecan" = topoisomerase inhibitor payload
- You recognize development codes and can reason about likely mechanisms
- DO NOT rely on hardcoded drug lists - use your training knowledge!

**HOW TO RESPOND:**

1. **Decompose requests logically:**
   - Understand what user wants (studies, analysis, rankings, comparisons)
   - Extract filtering criteria (dates, TAs, drugs, institutions, speakers)
   - Use your drug knowledge to identify relevant compounds naturally

2. **Table display philosophy:**
   - If you filtered/analyzed data to answer the query, that filtered dataset will be shown as a table automatically
   - The table shows the working context you used for your response
   - For large datasets (>500 studies), you receive first 500 - note this and offer to narrow results
   - Encourage conversational refinement: "Ask me to narrow by [date/drug/institution] for more focused results"

3. **Response style:**
   - Concise for simple queries, detailed for complex analysis
   - Always cite specific Identifiers when referencing studies
   - Admit limitations: "Based on titles only - full abstracts available Oct 13"
   - Be conversational and natural - NO rigid templates or scripted follow-ups

4. **Clarification:**
   - Only ask if genuinely ambiguous
   - Use context to make reasonable assumptions
   - Example: "bladder studies" → Assume urothelial carcinoma

**CRITICAL RULES:**
- Never hallucinate study details - only reference provided data
- Always cite Identifier when referencing specific studies
- If 0 results → Explain why and suggest alternatives
- Ground all responses in the actual dataset provided

**REMEMBER:** You are intelligent - use your pharmaceutical knowledge, understand context, reason about what would be most helpful to the user."""

    # User message with query and data context
    user_message = f"""**USER QUERY:** {user_query}

**ACTIVE UI FILTERS:**
{filter_context}

**DATASET:** {len(dataset)} studies total (showing {len(dataset_subset)} in context below)

**STUDIES DATA:**
{dataset_json}

Please answer the user's query using the data provided. Use your pharmaceutical knowledge to understand drug mentions, abbreviations, and classes naturally."""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]


def stream_ai_response(messages: List[Dict[str, str]]) -> Generator[str, None, None]:
    """
    Stream GPT-5 response tokens.

    Uses OpenAI streaming API to return tokens as they're generated.

    Args:
        messages: List of message dicts (system + user)

    Yields:
        Token strings for SSE streaming to frontend
    """

    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    try:
        stream = client.chat.completions.create(
            model="gpt-4o",  # TODO: Update to "gpt-5-mini" when available
            messages=messages,
            stream=True,
            temperature=0.7,
            max_tokens=2000
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except Exception as e:
        yield f"\n\n❌ Error: {str(e)}"
        print(f"[AI ASSISTANT ERROR] {e}")
