# Search Logic Analysis: Current vs Ideal

## Your Proposed Clean Logic

### Step 1: Query Assessment
**Goal**: Extract search intent and keywords from user query

**User Query**: "What are the studies on pembrolizumab and atezolizumab in bladder cancer?"

**AI Extraction** (single AI call):
```json
{
  "ta": "Bladder Cancer",
  "drugs": ["pembrolizumab", "atezolizumab"],
  "intent": "list_studies",
  "logic": "unclear"  // Needs clarification: AND or OR?
}
```

**Clarification** (if needed):
- "Do you want studies with **both drugs together** (combination) or **either drug** (separate studies)?"
- User responds: "Either drug" → Set `logic: "OR"`

### Step 2: Dataset Search
**Goal**: Find matching studies using simple keyword search

**Search Logic**:
```python
# Apply TA filter first
bladder_df = df[df['Title'].str.contains('bladder|urothelial', case=False)]

# Apply drug filter with OR logic
if logic == "OR":
    results = bladder_df[
        bladder_df['Title'].str.contains('pembrolizumab', case=False) |
        bladder_df['Title'].str.contains('atezolizumab', case=False)
    ]
elif logic == "AND":
    results = bladder_df[
        bladder_df['Title'].str.contains('pembrolizumab', case=False) &
        bladder_df['Title'].str.contains('atezolizumab', case=False)
    ]
```

**Result**: 45 studies with pembro OR atezo in bladder cancer

**Why check Drug CSV?** → **YOU DON'T NEED TO!** Just search titles directly.

### Step 3: Table Generation
**Goal**: Show results to user

```python
table = results[['Identifier', 'Title', 'Speakers', 'Affiliation', 'Session', 'Date', 'Time']]
display_table(table)
```

### Step 4: AI Synthesis
**Goal**: AI analyzes the table and provides insights

**Prompt**:
```
User asked: "What are the studies on pembrolizumab and atezolizumab in bladder cancer?"

Here are the 45 studies found:
[TABLE DATA]

Provide a brief summary of key findings, research themes, and notable studies.
```

**AI Response**: Natural language summary of the studies in the table.

---

## Current Implementation (Over-Engineered Mess)

### Current Flow for Same Query

#### Step 1a: Combination Detection
```python
combination_override = detect_unambiguous_combination(user_query)
# Checks for patterns like "EV + P", "nivo plus ipi"
# Result: None (doesn't match hardcoded patterns)
```

#### Step 1b: Ambiguity Detection
```python
ambiguous_check = detect_ambiguous_drug_query(user_query)
# Checks if "and" means combination or separate
# Result: Asks clarification (GOOD!)
```

#### Step 1c: AI Classification
```python
classification = classify_user_query(user_query, conversation_history)
# Calls GPT-5-mini to extract:
# {
#   "entity_type": "drug",
#   "search_terms": ["pembrolizumab", "atezolizumab"],
#   "generate_table": true,
#   "table_type": "drug_studies",
#   "filter_context": {"drug": "pembrolizumab", "ta": "bladder"},
#   "top_n": 20
# }
```

**Problem**: Already made 1 AI call just to extract keywords!

#### Step 2: Table Generation (generate_entity_table)
```python
# For drug_studies table:
table_html, table_data = generate_entity_table_drug_search(
    search_terms=['pembrolizumab', 'atezolizumab'],
    filtered_df=bladder_df,
    top_n=20
)
```

**What happens inside**:
1. Load Drug_Company_names.csv (400+ rows)
2. Loop through search terms: ["pembrolizumab", "atezolizumab"]
3. For each term, loop through 400+ drug DB rows
4. Check if "pembrolizumab" substring matches any drug name
5. Match found → Use "pembrolizumab" from DB
6. Repeat for "atezolizumab"
7. Search titles for matched drugs
8. Return 20 studies

**Why is this insane?**
- Drug DB has entries like: `Keytruda, pembrolizumab, Merck, ICI, PD-1 inhibitor`
- You're loading 400 rows just to confirm "pembrolizumab" → "pembrolizumab"
- **The user ALREADY typed "pembrolizumab"** - just search for that directly!

#### Step 3: Comprehensive Retrieval (retrieve_comprehensive_data)
```python
relevant_data = retrieve_comprehensive_data(
    user_query=user_query,
    filtered_df=bladder_df,
    classification=classification,
    max_studies=None
)
```

**What happens inside**:
1. Call GPT-5-nano to extract filter keywords: `["metastatic", "advanced"]`
2. Apply keyword filters to narrow dataset
3. Load Drug_Company_names.csv **AGAIN** (already loaded in Step 2!)
4. Loop through search terms **AGAIN**
5. Match drugs **AGAIN** (same logic as Step 2)
6. Search titles **AGAIN**
7. Return ALL matching studies (not limited to top_n)

**Why is this insane?**
- You just searched for drugs in Step 2!
- Now you're searching again for the SAME drugs
- You're loading the drug DB twice
- You're making another AI call (GPT-5-nano) just to extract "metastatic, advanced"

#### Step 4: AI Synthesis
```python
synthesis_prompt = build_synthesis_prompt_pre_abstract(
    user_query=user_query,
    relevant_data=relevant_data,  # ALL matching studies (not just table data!)
    classification=classification,
    verbosity='medium',
    intent='synthesis'
)
# Prompt length: 26,968 characters (includes 45 studies)

# Stream AI response
for token in stream_openai_tokens(synthesis_prompt, reasoning_effort='medium'):
    yield token
```

**Problem**: You're sending 45 full studies to the AI when you already showed a table of 20!

---

## The Core Issues

### Issue 1: Drug Database is Pointless for Search

**Current Logic**:
1. User types: "pembrolizumab"
2. Load 400-row drug CSV
3. Match "pembrolizumab" → "pembrolizumab" (identity match)
4. Search titles for "pembrolizumab"

**Simple Logic**:
1. User types: "pembrolizumab"
2. Search titles for "pembrolizumab"

**When Drug DB IS Useful**:
- Abbreviation expansion: User types "pembro" → Expand to "pembrolizumab"
- Commercial name mapping: User types "Keytruda" → Map to "pembrolizumab"
- MOA classification: User asks "show me ICIs" → Return all ICI drugs

**When Drug DB is NOT Useful**:
- User types full generic name: "pembrolizumab"
- User types full commercial name: "Keytruda"
- **Current code**: Uses DB even when not needed!

### Issue 2: Duplicate Drug Matching (2 Times!)

**Step 2** (`generate_entity_table`):
- Load Drug_Company_names.csv
- Match "pembrolizumab" → "pembrolizumab"
- Search titles

**Step 3** (`retrieve_comprehensive_data`):
- Load Drug_Company_names.csv **AGAIN**
- Match "pembrolizumab" → "pembrolizumab" **AGAIN**
- Search titles **AGAIN**

**Why?**: Because Step 2 generates a table (limited to top_n=20) and Step 3 retrieves ALL data for AI synthesis.

**Solution**: Do the search **ONCE**, then:
- Slice first 20 for table display
- Pass ALL results to AI synthesis

### Issue 3: Multiple AI Calls for Same Query

**AI Call 1** (`classify_user_query`): Extract keywords, intent, table type
- Model: GPT-5-mini
- Cost: ~$0.001

**AI Call 2** (`extract_filter_keywords_from_query`): Extract clinical setting keywords
- Model: GPT-5-nano
- Cost: ~$0.0001

**AI Call 3** (`stream_openai_tokens`): Generate synthesis response
- Model: GPT-5-mini with reasoning
- Cost: ~$0.10

**Total**: 3 AI calls, $0.10 per query

**Solution**: Combine AI Call 1 + 2 into single classification call. Only AI Call 3 is needed for synthesis.

### Issue 4: Over-Complicated Prompt Building

**Current synthesis prompt**:
```
User asked: "What are the studies on pembrolizumab and atezolizumab?"

**CLASSIFICATION**: {"entity_type": "drug", "search_terms": ["pembrolizumab", "atezolizumab"], ...}

**INTENT**: {"intent": "synthesis", "verbosity": "medium"}

**FILTER CONTEXT**: TA filter applied, 447 bladder studies

**TABLE DATA** (20 studies):
[Markdown table]

**COMPREHENSIVE DATA** (45 studies):
[Full study list with titles, speakers, affiliations]

**SYNTHESIS INSTRUCTIONS**:
- Analyze the data
- Identify key themes
- Highlight notable studies
- Provide actionable insights
- ...
```

**Simple prompt**:
```
User asked: "What are the studies on pembrolizumab and atezolizumab in bladder cancer?"

Here are the 45 studies found:
[Table with Identifier, Title, Speakers]

Provide a brief summary of research themes and notable studies.
```

**Difference**: 26,000 chars → 5,000 chars (80% reduction)

---

## Proposed Simplified Architecture

### Function 1: `extract_search_intent(user_query)` - Single AI Call
```python
def extract_search_intent(user_query: str) -> dict:
    """
    Single AI call to extract all search intent.
    Replaces: classify_user_query + extract_filter_keywords_from_query + detect_query_intent
    """
    prompt = f"""Extract search intent from this conference query:

User Query: "{user_query}"

Return JSON:
{{
  "ta": "Bladder Cancer" or null,
  "drugs": ["drug1", "drug2"] or [],
  "speakers": ["name"] or [],
  "affiliations": ["institution"] or [],
  "sessions": ["oral", "poster"] or [],
  "dates": ["Day 1"] or [],
  "biomarkers": ["FGFR3", "PD-L1"] or [],
  "logic": "AND" or "OR" or "unclear",
  "intent": "list_studies" or "compare_drugs" or "synthesize",
  "needs_clarification": true/false,
  "clarification_question": "..." or null
}}

Rules:
- For "pembro", expand to "pembrolizumab"
- For "Keytruda", expand to "pembrolizumab"
- For "ADC", list all ADC drugs: ["enfortumab vedotin", "sacituzumab govitecan", "trastuzumab deruxtecan"]
- If user says "X and Y", set logic to "unclear" and ask: "Combination or separate studies?"
- If user says "X + Y" or "X plus Y", set logic to "AND" (combination)
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=[{"role": "user", "content": prompt}],
        reasoning={"effort": "low"}
    )

    return json.loads(response.output_text)
```

**Result**: 1 AI call instead of 3

### Function 2: `search_conference_data(intent, df)` - Simple Title Search
```python
def search_conference_data(intent: dict, df: pd.DataFrame) -> pd.DataFrame:
    """
    Simple keyword search. No drug database needed unless abbreviation expansion required.
    """
    results = df.copy()

    # Apply TA filter
    if intent['ta']:
        ta_keywords = ESMO_THERAPEUTIC_AREAS.get(intent['ta'], {}).get('keywords', [])
        mask = pd.Series([False] * len(results))
        for keyword in ta_keywords:
            mask |= results['Title'].str.contains(keyword, case=False, na=False)
        results = results[mask]

    # Apply drug filter
    if intent['drugs']:
        mask = pd.Series([False] * len(results))
        for drug in intent['drugs']:
            mask |= results['Title'].str.contains(drug, case=False, na=False)

        # Apply AND/OR logic
        if intent['logic'] == 'AND':
            # For AND logic, all drugs must be present
            mask = pd.Series([True] * len(results))
            for drug in intent['drugs']:
                mask &= results['Title'].str.contains(drug, case=False, na=False)

        results = results[mask]

    # Apply speaker filter
    if intent['speakers']:
        mask = pd.Series([False] * len(results))
        for speaker in intent['speakers']:
            mask |= results['Speakers'].str.contains(speaker, case=False, na=False)
        results = results[mask]

    # ... (similar for affiliations, sessions, dates, biomarkers)

    return results
```

**Result**: Simple pandas filtering, no drug database needed!

### Function 3: `generate_table_and_synthesis(user_query, results)` - Single AI Call
```python
def generate_table_and_synthesis(user_query: str, results: pd.DataFrame):
    """
    Show table + AI synthesis in one go.
    """
    # Display table (first 20 results)
    table_data = results.head(20)[['Identifier', 'Title', 'Speakers', 'Affiliation', 'Session']]
    yield {"type": "table", "data": table_data.to_dict('records')}

    # AI synthesis (use ALL results, not just first 20)
    synthesis_prompt = f"""User asked: "{user_query}"

Here are the {len(results)} studies found:

{results[['Identifier', 'Title', 'Speakers']].to_markdown()}

Provide a concise summary of research themes and notable studies."""

    for token in stream_openai_tokens(synthesis_prompt):
        yield {"type": "text", "text": token}
```

**Result**: 1 AI call for synthesis, clean prompt

---

## When to Use Drug Database

### Use Case 1: Abbreviation Expansion
**User Query**: "Show me pembro studies"

**Logic**:
1. Check if "pembro" is in drug DB abbreviations → YES
2. Expand to "pembrolizumab"
3. Search titles for "pembrolizumab"

### Use Case 2: Commercial Name Mapping
**User Query**: "What's new with Keytruda?"

**Logic**:
1. Check if "Keytruda" is in drug DB commercial names → YES
2. Map to generic: "pembrolizumab"
3. Search titles for "pembrolizumab"

### Use Case 3: Drug Class Queries
**User Query**: "Show me all ADC studies"

**Logic**:
1. Query drug DB where MOA_Class = "ADC"
2. Get list: ["enfortumab vedotin", "sacituzumab govitecan", "trastuzumab deruxtecan", ...]
3. Search titles for ANY of these drugs (OR logic)

### Use Case 4: Adding MOA Info to Results
**After finding studies**:
1. Match study drugs to drug DB
2. Append MOA columns: `MOA_Class`, `MOA_Target`, `Company`
3. Display enriched table

**Example**:
| Identifier | Title | Drug | MOA Class | Company |
|------------|-------|------|-----------|---------|
| LBA1 | EV+P in 1L mUC | Enfortumab Vedotin | ADC | Seagen |

---

## Recommendation: Hybrid Approach

### Step 1: Smart Drug Matching (Only When Needed)
```python
def expand_drug_query(user_drugs: list) -> list:
    """
    Expand abbreviations and commercial names to generic names.
    ONLY call if user query contains potential abbreviations.
    """
    expanded_drugs = []

    for drug in user_drugs:
        # Check if it's a known abbreviation or commercial name
        match = drug_db[
            (drug_db['drug_commercial'].str.lower() == drug.lower()) |
            (drug_db['abbreviation'].str.lower() == drug.lower())
        ]

        if not match.empty:
            # Use generic name
            expanded_drugs.append(match.iloc[0]['drug_generic'])
        else:
            # Use as-is (might be full generic name already)
            expanded_drugs.append(drug)

    return expanded_drugs
```

**When to call**:
- User types short string (< 10 chars): "pembro", "EV", "nivo"
- User types capital acronym: "ADC", "ICI", "TKI"
- User types commercial name: "Keytruda", "Opdivo"

**When NOT to call**:
- User types full generic name: "pembrolizumab", "enfortumab vedotin"
- User types scientific term: "FGFR3", "PD-L1"

### Step 2: Single Search Function
```python
def search_studies(intent: dict, df: pd.DataFrame) -> pd.DataFrame:
    """
    One search function to rule them all.
    """
    # Expand abbreviations if needed
    if intent['drugs']:
        intent['drugs'] = expand_drug_query(intent['drugs'])

    # Simple title search with AND/OR logic
    results = apply_filters(df, intent)

    return results
```

### Step 3: Optional MOA Enrichment
```python
def enrich_with_moa(results: pd.DataFrame) -> pd.DataFrame:
    """
    After finding studies, add MOA info from drug DB.
    """
    # Extract drugs from titles
    results['Drug'] = results['Title'].apply(extract_drug_from_title)

    # Match to drug DB
    results = results.merge(
        drug_db[['drug_generic', 'moa_class', 'moa_target', 'company']],
        left_on='Drug',
        right_on='drug_generic',
        how='left'
    )

    return results
```

---

## Summary: What Needs to Change

### Remove Completely
1. ✅ **Duplicate drug matching** in `retrieve_comprehensive_data` (already done in `generate_entity_table`)
2. ✅ **extract_filter_keywords_from_query** (merge into `classify_user_query`)
3. ✅ **detect_query_intent** (merge into `classify_user_query`)
4. ✅ **Drug DB loading twice** (load once, cache in memory)

### Simplify Dramatically
1. **classify_user_query**: Single AI call to extract ALL intent (TA, drugs, speakers, logic, clarification)
2. **search_studies**: Simple pandas filtering with keyword matching
3. **expand_drug_query**: Only call if abbreviation/commercial name detected
4. **generate_synthesis**: Clean prompt with table data only

### Keep & Enhance
1. **detect_ambiguous_drug_query**: Good for clarification (keep!)
2. **Drug DB for abbreviation expansion**: Keep for "pembro" → "pembrolizumab"
3. **Drug DB for MOA enrichment**: Keep for adding MOA columns to results
4. **ESMO_THERAPEUTIC_AREAS**: Keep for TA keyword matching

---

## Expected Performance Improvement

| Metric | Current | Proposed | Improvement |
|--------|---------|----------|-------------|
| **AI Calls per Query** | 3 (classify + extract + synthesize) | 1 (synthesize only) | 67% reduction |
| **Drug DB Loads** | 2 (table gen + retrieval) | 1 (if abbreviation detected) | 50-100% reduction |
| **Search Operations** | 2 (table + retrieval) | 1 (single search) | 50% reduction |
| **Prompt Length** | 26,000 chars | 5,000 chars | 80% reduction |
| **Response Time** | 15-30 seconds | 5-10 seconds | 67% faster |
| **Code Complexity** | 500 lines across 5 functions | 200 lines across 3 functions | 60% simpler |

---

## Next Steps

1. **Review this analysis** - Confirm approach makes sense
2. **Decide on refactor scope** - Full rewrite or incremental fixes?
3. **Priority bugs** - Fix empty string matching first (already done!)
4. **Simplify search** - Combine duplicate drug matching
5. **Merge AI calls** - Single classification call
6. **Test & validate** - Ensure accuracy maintained

Should we proceed with full refactor or fix critical bugs first?
