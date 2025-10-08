# Phase 1: Core AI Assistant Module
## Detailed Implementation Plan (Aligned with The Bible)

---

## Objective

Create a single, clean `ai_assistant.py` module that:
1. Handles all chat queries with AI-first approach
2. **NO drug expansion** - AI handles naturally via GPT-5 training knowledge
3. Does basic search for token efficiency (optional pre-filtering)
4. Sends context to AI and streams response
5. AI decides when to show tables vs. suggest Data Explorer

**Code target:** ~200 lines (vs. 1,500 lines in old system)

---

## File: `ai_assistant.py` Structure

```python
"""
AI-First Chat Assistant for Conference Intelligence
====================================================

Philosophy: LET THE AI BE THE INTELLIGENCE
- AI handles drug knowledge, understanding, classification
- We provide: data grounding, UI filters, basic search
- NO hardcoded drug expansion, intent classification, or rigid rules

Functions:
- handle_chat_query() - Main entry point
- basic_search() - Optional text search to narrow dataset
- prepare_ai_context() - Format data for GPT-5 prompt
- stream_ai_response() - GPT-5 streaming with system prompt
"""

import pandas as pd
from typing import Dict, List, Optional, Any, Generator
import re
from openai import OpenAI
import os
```

---

## Function 1: `handle_chat_query()`

**Purpose:** Main orchestrator - minimal logic, AI does the heavy lifting

```python
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
    ai_prompt = prepare_ai_context(
        user_query=user_query,
        dataset=relevant_df,
        filters=active_filters
    )

    # Step 3: Stream GPT-5 response
    response_generator = stream_ai_response(ai_prompt)

    return {
        'type': 'ai_response',
        'filtered_data': relevant_df,  # AI may instruct frontend to show this as table
        'response_stream': response_generator
    }
```

---

## Function 2: `basic_search()`

**Purpose:** Simple text search to narrow dataset for token efficiency (NOT restrictive filtering)

```python
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
        'sessions', 'studies', 'presentations', 'data'
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
```

---

## Function 3: `prepare_ai_context()`

**Purpose:** Format data and create GPT-5 system prompt (The Bible's instructions)

```python
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

2. **Decide whether to show table in your response:**

   **SHOW TABLE when:**
   - Contextual queries (drug/institution/speaker/TA-specific) - e.g., "What is pembrolizumab?" → answer + show pembro studies
   - Multi-dimensional queries with focused results - e.g., "Pembrolizumab at MD Anderson" → ~20 studies
   - Analytical queries needing data reference - e.g., comparisons, rankings

   **Table handling for large results:**
   - If >500 studies match, you'll receive first 500 in context
   - Note: "Showing first 500 of X total. Ask me to narrow by [criteria] for focused results."
   - Encourage conversational refinement rather than overwhelming with data

   **Format when showing table:**
   Return JSON response:
   ```json
   {
     "response": "Your natural language answer...",
     "show_table": true,
     "table_note": "The table below shows all 127 pembrolizumab studies at ESMO 2025"
   }
   ```

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
```

---

## Function 4: `stream_ai_response()`

**Purpose:** Stream tokens from GPT-5

```python
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
            model="gpt-4o",  # UPDATE: Will use "gpt-5-mini" when available
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
```

---

## What We're REUSING from Current System

1. **Search Text Precomputation**:
   - `search_text_normalized` column on DataFrame (from improved_search.py)
   - Enables fast multi-field text search

2. **UI Filter Logic** (from app.py):
   - `get_filtered_dataframe_multi()` - Apply UI filters before passing to AI
   - TA filters, drug filters, session/date filters

3. **Flask SSE Streaming Pattern** (from current endpoints):
   - Stream AI response tokens to frontend in real-time

---

## What We're DELETING

❌ `drug_utils.py` - Drug expansion (AI knows drugs naturally)
❌ `entity_resolver.py` (400 lines) - Drug/institution extraction (AI handles)
❌ `query_intelligence.py` (200 lines) - Intent classification (AI understands)
❌ `enhanced_search.py` (400 lines) - Complex search pipeline (basic search + AI)
❌ `lean_synthesis.py` (300 lines) - Token optimization logic (AI decides verbosity)

**Total code reduction:** ~1,500 lines → ~200 lines

---

## Testing Strategy for Phase 1

Test queries from The Bible:

```python
test_queries = [
    # Drug queries (test AI's pharmaceutical knowledge)
    "What is pembrolizumab?",  # Should show drug info + table of studies
    "Show me ADC studies in breast cancer",  # AI knows ADC = antibody-drug conjugates
    "EV + P data updates",  # AI knows EV = enfortumab vedotin, P = pembrolizumab

    # Institution queries
    "What's MD Anderson presenting?",  # Should show table of MD Anderson studies

    # Date queries (large result sets)
    "Sessions on 10/19",  # Should show first 500 + offer refinement

    # Multi-dimensional
    "Pembrolizumab studies at MD Anderson",  # Focused table

    # Analytical
    "Top 20 most active authors",  # AI counts/ranks from data

    # Competitive intelligence
    "Bladder cancer immunotherapy combinations",  # Should contextualize vs. Bavencio
]
```

---

## Success Criteria for Phase 1

Before moving to Phase 2, verify:

✅ `ai_assistant.py` created (~200 lines)
✅ NO drug expansion - AI uses training knowledge
✅ Basic search works (broad, not over-filtering)
✅ GPT-5 system prompt includes all Bible instructions
✅ AI pharmaceutical knowledge works (recognizes "EV", "ADC", etc.)
✅ Streaming works with OpenAI
✅ Table data returned for frontend to display when appropriate
✅ Test queries return intelligent, grounded responses

---

**Next:** Implement ai_assistant.py aligned with The Bible
