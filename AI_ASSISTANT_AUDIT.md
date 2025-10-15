# AI Assistant Audit Report
**Date:** October 15, 2025
**File:** `ai_first_refactor/ai_assistant.py`
**Issue:** Conceptual queries not searching dataset properly

---

## EXECUTIVE SUMMARY

**Problem**: When user asks "What is zelenectide vedotin?", the system responds with "I'm not finding a match" instead of:
1. Extracting "zelenectide vedotin" as a search keyword
2. Searching the dataset for matching studies
3. Answering the question using medical knowledge + found studies as supporting evidence

**Root Cause**: The query interpreter (Step 1) is classifying "What is X?" questions as `conceptual_query` with `retrieve_supporting_studies: false`, which skips dataset search entirely.

**Impact**: Users cannot discover conference studies about drugs/topics they're asking about. The system acts like a medical encyclopedia instead of a conference intelligence tool.

---

## CURRENT BEHAVIOR (BROKEN)

### User Query: "What is zelenectide vedotin?"

**Step 1 - Query Interpretation:**
```json
{
  "response_type": "conceptual_query",
  "topic": "Zelenectide vedotin drug information",
  "context_entities": [],
  "retrieve_supporting_studies": false
}
```

**Step 2 - Dataset Filtering:**
```python
# SKIPPED - retrieve_supporting_studies is false
filtered_df = pd.DataFrame()  # Empty!
```

**Step 3 - AI Response:**
- AI answers from medical knowledge only
- No dataset search performed
- No table generated
- User message: "I'm not finding a match for zelenectide vedotin"

**Result**: User gets ZERO conference intelligence. System fails primary job.

---

## DESIRED BEHAVIOR (WHAT USER EXPECTS)

### User Query: "What is zelenectide vedotin?"

**Step 1 - Query Interpretation:**
```json
{
  "response_type": "conceptual_query",
  "topic": "Zelenectide vedotin ADC drug",
  "context_entities": ["zelenectide vedotin", "zelenectide", "vedotin"],
  "retrieve_supporting_studies": true  // ALWAYS TRUE for drug/entity queries
}
```

**Step 2 - Dataset Filtering:**
```python
# Search for "zelenectide vedotin", "zelenectide", or "vedotin"
entity_pattern = 'zelenectide vedotin|zelenectide|vedotin'
filtered_df = df[df['Title'].str.contains(entity_pattern, case=False, na=False, regex=True)]
# Result: 3 studies found
```

**Step 3 - AI Response:**
```
Zelenectide vedotin is an antibody-drug conjugate (ADC) targeting B7-H3 (CD276),
designed for solid tumor treatment. At ESMO 2025, there are 3 studies presenting
data on zelenectide vedotin:

**Study 1234P**: Phase 2 trial in metastatic NSCLC showing ORR of 35%...
**Study 5678P**: Safety analysis across solid tumors...
**Study 9012P**: Biomarker analysis of B7-H3 expression...

[Table with 3 studies shown above]

These results suggest zelenectide vedotin may offer activity in B7-H3+ tumors...
```

**Result**: User gets BOTH knowledge answer AND conference intelligence.

---

## ROOT CAUSE ANALYSIS

### Issue 1: Conceptual Query Classification Too Broad

**Location:** Lines 306-313 (extract_search_keywords_from_ai)

**Current Prompt:**
```
**Option 3 - Conceptual/Strategic Question**:
- Mechanism questions: "What is the difference between X and Y?", "How does X work?", "What's the MOA of X?"
- Background questions: "Tell me about X", "What is X used for?"
- Set "retrieve_supporting_studies" to TRUE if studies would add value
- Set to FALSE if it's pure knowledge question
```

**Problem**: The AI interprets "What is zelenectide vedotin?" as a "pure knowledge question" because:
1. It's a definition request ("What is X?")
2. The drug name is unfamiliar to the AI
3. The AI defaults to `retrieve_supporting_studies: false` for unknown entities

**Why This Is Wrong**:
- In a **conference intelligence app**, EVERY entity query should search the dataset
- "What is X?" should mean "Tell me about X AND show me conference data on X"
- The default should be `retrieve_supporting_studies: true` for all drug/biomarker/entity queries

---

### Issue 2: Context Entities Not Extracted Properly

**Location:** Lines 109-113 (handle_chat_query)

**Current Code:**
```python
context_entities = interpretation.get('context_entities', [])
retrieve_studies = interpretation.get('retrieve_supporting_studies', False)

# If AI wants supporting studies, filter by context entities
if retrieve_studies and context_entities:
    # Search for entities
```

**Problem**: Even if `retrieve_supporting_studies: true`, the AI must ALSO populate `context_entities` list. For "What is zelenectide vedotin?", the AI should return:
```json
"context_entities": ["zelenectide vedotin", "zelenectide", "vedotin"]
```

But currently returns:
```json
"context_entities": []
```

**Why This Happens**: The prompt examples don't show how to extract entities from "What is X?" queries.

---

### Issue 3: Filtering Logic Too Restrictive

**Location:** Lines 116-122 (handle_chat_query)

**Current Code:**
```python
if retrieve_studies and context_entities:
    entity_pattern = '|'.join([re.escape(e) for e in context_entities])
    filtered_df = df[
        df['Title'].str.contains(entity_pattern, case=False, na=False, regex=True)
    ]
else:
    filtered_df = pd.DataFrame()  # Empty!
```

**Problem**: If EITHER condition is false, no search happens:
- `retrieve_studies = false` → No search
- `context_entities = []` → No search

**Better Approach**: Extract entity from query ALWAYS, search ALWAYS, let AI decide how to use results.

---

## RECOMMENDED FIXES

### Fix 1: Change Default Behavior for Entity Queries

**Principle**: In a conference intelligence app, ALWAYS search the dataset for entities mentioned in the query.

**Location:** Lines 306-313 prompt

**Before:**
```
**Option 3 - Conceptual/Strategic Question**:
- Set "retrieve_supporting_studies" to TRUE if studies would add value
- Set to FALSE if it's pure knowledge question
```

**After:**
```
**Option 3 - Conceptual/Strategic Question**:
CRITICAL: If the query mentions ANY specific entity (drug, biomarker, pathway, institution, person):
- Set "retrieve_supporting_studies" to TRUE (default for entity queries)
- Populate "context_entities" with the entity name and common variants/abbreviations
- Examples:
  * "What is zelenectide vedotin?" → context_entities: ["zelenectide vedotin", "zelenectide", "vedotin"]
  * "Tell me about METex14" → context_entities: ["METex14", "MET exon 14", "MET exon 14 skipping"]
  * "What's the MOA of tepotinib?" → context_entities: ["tepotinib"]

Only set "retrieve_supporting_studies" to FALSE for pure mechanism questions with NO specific entities:
- "What is the difference between PD-1 and PD-L1?" (class comparison, not specific drug)
- "How do checkpoint inhibitors work?" (mechanism category, not specific drug)
```

---

### Fix 2: Add Fallback Entity Extraction

**Principle**: If AI fails to extract entities, fallback to simple regex extraction from user query.

**Location:** After line 113 in handle_chat_query

**Add:**
```python
# If AI wants supporting studies, filter by context entities
if retrieve_studies and context_entities:
    print(f"[STEP 2] Filtering for supporting studies about: {', '.join(context_entities)}")
    entity_pattern = '|'.join([re.escape(e) for e in context_entities])
    filtered_df = df[
        df['Title'].str.contains(entity_pattern, case=False, na=False, regex=True)
    ]
    print(f"[STEP 2] Filtered: {len(df)} -> {len(filtered_df)} supporting studies")
elif retrieve_studies and not context_entities:
    # FALLBACK: AI said to retrieve studies but didn't extract entities
    # Extract potential entities from user query using simple heuristics
    print(f"[STEP 2] FALLBACK: AI requested studies but no entities extracted")
    print(f"[STEP 2] Attempting entity extraction from query: '{user_query}'")

    # Remove question words and common patterns
    query_clean = re.sub(r'\b(what|is|the|a|an|about|tell me|show me|find)\b', '', user_query, flags=re.IGNORECASE)
    query_clean = query_clean.strip(' ?.,')

    # Extract potential drug names (capitalized words, words ending in -mab/-nib/-tinib/-vedotin)
    drug_pattern = r'\b([A-Z][a-z]+(?:mab|nib|tinib|vedotin|zumab|mumab))\b|\b([A-Z][a-z]{4,})\b'
    potential_drugs = re.findall(drug_pattern, query_clean)
    potential_drugs = [d for group in potential_drugs for d in group if d]

    if potential_drugs:
        print(f"[STEP 2] FALLBACK: Extracted potential entities: {potential_drugs}")
        entity_pattern = '|'.join([re.escape(e) for e in potential_drugs])
        filtered_df = df[
            df['Title'].str.contains(entity_pattern, case=False, na=False, regex=True)
        ]
        print(f"[STEP 2] FALLBACK: Filtered: {len(df)} -> {len(filtered_df)} supporting studies")
    else:
        print(f"[STEP 2] FALLBACK: Could not extract entities - returning empty dataset")
        filtered_df = pd.DataFrame()
else:
    # No study filtering needed - AI will answer from knowledge
    filtered_df = pd.DataFrame()
    print(f"[STEP 2] No study filtering needed - conceptual answer from medical knowledge")
```

---

### Fix 3: Update Prompt Examples for Entity Extraction

**Location:** Lines 360-363 prompt examples

**Add these examples:**
```
Drug/Entity Information Queries (ALWAYS retrieve studies):
"What is zelenectide vedotin?" → {"response_type": "conceptual_query", "topic": "Zelenectide vedotin ADC drug", "context_entities": ["zelenectide vedotin", "zelenectide", "vedotin"], "retrieve_supporting_studies": true}
"Tell me about tepotinib" → {"response_type": "conceptual_query", "topic": "Tepotinib MET inhibitor", "context_entities": ["tepotinib"], "retrieve_supporting_studies": true}
"What is METex14?" → {"response_type": "conceptual_query", "topic": "MET exon 14 skipping mutation", "context_entities": ["METex14", "MET exon 14", "MET exon 14 skipping"], "retrieve_supporting_studies": true}

Pure Mechanism Questions (no studies needed):
"What is the difference between PD-1 and PD-L1 inhibitors?" → {"response_type": "conceptual_query", "topic": "Mechanism difference between PD-1 vs PD-L1 checkpoint inhibitors", "context_entities": [], "retrieve_supporting_studies": false}
"How do checkpoint inhibitors work?" → {"response_type": "conceptual_query", "topic": "Checkpoint inhibitor mechanism of action", "context_entities": [], "retrieve_supporting_studies": false}
```

---

### Fix 4: Update AI Response Framing for Conceptual Queries with Studies

**Location:** Lines 758-769 (user_message building for conceptual_query)

**Before:**
```python
if len(filtered_df) > 0:
    user_message = f"""**User Question:** {user_query}

**Supporting Context:** {len(filtered_df)} related studies are available as supporting evidence (if relevant to your answer).

**Studies Available:**
{dataset_json}

Answer the user's question directly using your medical knowledge. Use the studies above as supporting evidence only if they add value."""
```

**After:**
```python
if len(filtered_df) > 0:
    user_message = f"""**User Question:** {user_query}

**Conference Intelligence Context:** I found {len(filtered_df)} studies at ESMO 2025 related to this topic.

**IMPORTANT RESPONSE STRUCTURE:**
1. Start by answering the user's question directly (definition, mechanism, background)
2. Then transition: "At ESMO 2025, there are {len(filtered_df)} studies on this topic:"
3. Briefly highlight 1-3 key studies with Identifiers and main findings
4. Provide strategic context if relevant to EMD portfolio
5. Note: A table of all {len(filtered_df)} studies will be shown above your response

**Studies Available:**
{dataset_json}

Answer the user's question using BOTH your medical knowledge AND the conference studies above. Always cite study Identifiers when referencing data."""
```

---

## TESTING PLAN

### Test Case 1: Unknown Drug Query
**Input:** "What is zelenectide vedotin?"

**Expected Behavior:**
- Step 1: `conceptual_query`, `context_entities: ["zelenectide vedotin", "zelenectide", "vedotin"]`, `retrieve_supporting_studies: true`
- Step 2: Search dataset, find N studies
- Step 3: Answer definition + describe N studies

**Success Criteria:**
- ✅ Table displayed with matching studies
- ✅ AI response includes both definition and conference data
- ✅ Study Identifiers cited

---

### Test Case 2: Known Drug Query
**Input:** "Tell me about tepotinib"

**Expected Behavior:**
- Step 1: `conceptual_query`, `context_entities: ["tepotinib"]`, `retrieve_supporting_studies: true`
- Step 2: Search dataset, find ~10 tepotinib studies
- Step 3: Answer with EMD asset context + ESMO studies

**Success Criteria:**
- ✅ Table displayed with tepotinib studies
- ✅ AI mentions tepotinib as EMD asset (Tepmetko, MET inhibitor, NSCLC)
- ✅ Highlights key ESMO presentations

---

### Test Case 3: Pure Mechanism Query
**Input:** "What is the difference between PD-1 and PD-L1 inhibitors?"

**Expected Behavior:**
- Step 1: `conceptual_query`, `context_entities: []`, `retrieve_supporting_studies: false`
- Step 2: No dataset search
- Step 3: Pure knowledge answer about mechanism difference

**Success Criteria:**
- ✅ No table displayed
- ✅ AI explains PD-1 vs PD-L1 mechanism
- ✅ May mention avelumab (EMD's PD-L1 inhibitor) as example

---

### Test Case 4: Biomarker Query
**Input:** "What is METex14?"

**Expected Behavior:**
- Step 1: `conceptual_query`, `context_entities: ["METex14", "MET exon 14", "MET exon 14 skipping"]`, `retrieve_supporting_studies: true`
- Step 2: Search dataset, find METex14 studies
- Step 3: Answer biomarker definition + tepotinib studies (EMD's METex14 drug)

**Success Criteria:**
- ✅ Table displayed with METex14 studies
- ✅ AI explains METex14 is actionable mutation in NSCLC
- ✅ Highlights tepotinib VISION studies

---

## IMPLEMENTATION PRIORITY

### CRITICAL (Fix Immediately):
1. **Fix 1**: Update prompt to default `retrieve_supporting_studies: true` for entity queries
2. **Fix 3**: Add entity extraction examples to prompt

### HIGH (Next Sprint):
3. **Fix 2**: Add fallback entity extraction from user query
4. **Fix 4**: Update response framing to emphasize conference intelligence

### MEDIUM (Future Enhancement):
5. Add validation logging: Log when AI fails to extract entities for "What is X?" queries
6. Add retry logic: If no studies found, try broader search (partial matches, abbreviations)
7. Build drug/biomarker synonym dictionary for better matching

---

## CODE CHANGES REQUIRED

### Change 1: Update Prompt (Lines 306-313)

**File:** ai_first_refactor/ai_assistant.py
**Function:** extract_search_keywords_from_ai

Replace lines 306-313 with updated prompt from Fix 1 above.

---

### Change 2: Add Examples (After Line 363)

**File:** ai_first_refactor/ai_assistant.py
**Function:** extract_search_keywords_from_ai

Add drug/entity query examples from Fix 3 above.

---

### Change 3: Add Fallback Extraction (After Line 113)

**File:** ai_first_refactor/ai_assistant.py
**Function:** handle_chat_query

Add fallback entity extraction code from Fix 2 above.

---

### Change 4: Update Response Framing (Lines 758-769)

**File:** ai_first_refactor/ai_assistant.py
**Function:** analyze_filtered_results_with_ai

Replace conceptual query user_message with updated version from Fix 4 above.

---

## SUMMARY

**Current State**: AI assistant treats "What is X?" as pure knowledge query, never searches conference data.

**Desired State**: AI assistant ALWAYS searches conference data for entity queries, answers with BOTH knowledge + conference intelligence.

**Key Changes**:
1. Default `retrieve_supporting_studies: true` for entity queries
2. Always extract entity names into `context_entities`
3. Add fallback entity extraction
4. Frame responses to emphasize conference intelligence + table

**Impact**: Transforms system from "medical encyclopedia" to "conference intelligence platform" - users get both answers AND data.

---

**Audit Completed:** October 15, 2025
**Status:** Ready for implementation
**Risk:** LOW (changes only affect query interpretation logic, no database/API changes)
