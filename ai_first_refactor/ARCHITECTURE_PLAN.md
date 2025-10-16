# AI-First Architecture Plan
## Complete Refactor - Clean, Simple, AI-Driven

---

## Core Philosophy

**LET THE AI BE THE INTELLIGENCE**
- Minimal hardcoding
- Maximum flexibility
- AI handles understanding, classification, reasoning
- **CRITICAL:** AI handles drug knowledge naturally - NO hardcoded expansion
- We only provide: data grounding, UI filters, basic search

---

## Complete Architecture

### Files Structure (Minimal)

```
conference_intelligence_app/
├── app.py                          # Main Flask app (keep Data Explorer untouched)
├── ai_assistant.py                 # NEW: AI-first chat logic (replaces 6 modules)
├── templates/
│   └── index.html                  # Frontend (minimal changes)
├── static/
│   ├── js/app.js                   # Frontend JS (update endpoint)
│   └── css/styles.css              # No changes
├── ESMO_2025_FINAL_20250929.csv    # Conference data
└── competitive landscape JSONs      # Keep as-is
```

**DELETED:**
- entity_resolver.py (400 lines → AI handles it)
- query_intelligence.py (200 lines → AI handles it)
- enhanced_search.py (400 lines → AI handles it)
- lean_synthesis.py (300 lines → AI handles it)
- drug_utils.py (drug expansion → AI handles it naturally)
- improved_search.py (partial - keep only search_text precomputation)

---

## New AI Assistant Flow

```python
User Query → AI Assistant (ai_assistant.py)
    ↓
1. Apply UI filters (bladder, lung, etc.)
   - Simple DataFrame filter from user selection

2. Basic search (optional, to narrow dataset)
   - Simple text search if query has obvious keywords
   - DON'T over-filter - let AI do fine-grained filtering
   - AI handles drug understanding naturally (no expansion needed)

3. Send to AI with full context
   - System prompt: Role, tone, capabilities
   - Dataset: Relevant studies (as JSON)
   - Columns available: Title, Speakers, Date, etc.
   - User query: Exactly as asked

4. AI responds with:
   - Natural language answer
   - Specific study references
   - Aggregations/rankings if needed
   - Clarifications if query unclear
   - AI uses its training knowledge for drugs/abbreviations

5. Return to frontend:
   - Table: Filtered dataset for UI display
   - AI Response: Streamed text
```

---

## What AI Handles (No Hardcoding)

✅ **Intent Understanding**
   - "Show me" vs "Tell me about" vs "What are the top"
   - No pre-classification needed

✅ **Response Style**
   - Concise vs comprehensive based on context
   - User can request: "Give me a brief summary" or "detailed analysis"

✅ **Clarification Requests**
   - AI decides if query is too vague
   - AI asks follow-up questions naturally

✅ **Aggregation & Analysis**
   - "Top 20 authors" → AI counts and ranks
   - "Sessions on 10/18" → AI filters by date
   - "MD Anderson studies" → AI searches affiliations

✅ **Meta Queries**
   - "What can you do?" → AI explains capabilities
   - "How does this work?" → AI describes process

---

## What We Handle (Minimal Hardcoding)

🔧 **Basic Search**
   - Extract obvious search terms from query
   - Broad text search to narrow dataset (not restrictive)
   - Pass relevant subset to AI (token efficiency)

🔧 **UI Filters**
   - Bladder, Lung, CRC filters from UI
   - Date, Session type filters
   - Applied before AI sees data

🔧 **Table Generation**
   - Return actual CSV rows for UI display
   - Prevent hallucinations - show real data

---

## 🚨 CRITICAL: NO Drug Expansion Hardcoding

**User's Core Reasoning:**
"If we're using a model with high reasoning, do we even need the 'expand drug abbreviations' script? If I ask you about 'EV + P' you know what I am talking about. I would much rather the AI use its brain here too."

**Why This Is The Right Call:**

1. **AI Already Knows Drug Nomenclature**
   - GPT-5 training data includes drug databases, clinical trials, medical literature
   - Understands abbreviations: "EV" = enfortumab vedotin, "P" = pembrolizumab
   - Knows drug classes: "ADC" = antibody-drug conjugates
   - Recognizes naming patterns: "-mab" = antibody, "-tinib" = kinase inhibitor

2. **Conference Reality: Bleeding Edge Science**
   - ESMO presents novel compounds with development codes
   - Example: "M9144", "SG-3249", "ARX788"
   - How would our hardcoded CSV know these are ADCs?
   - **The AI can reason from context and naming patterns**

3. **Proof of AI Understanding**
   - Test query: "What is gleecotamab gonetecan?"
   - AI correctly identified: ADC (antibody-drug conjugate)
   - Reasoning: "-mab" suffix (antibody) + "-tecan" suffix (topoisomerase inhibitor payload)
   - **No hardcoded list needed!**

4. **Hardcoded Lists Are Restrictive**
   - Our CSV has 56 ADC drugs (outdated the moment it's created)
   - New ADCs approved/developed every month
   - AI's training data >>> our Excel spreadsheet
   - Hardcoding creates false negatives and maintenance burden

5. **Let AI Use Its "Brain"**
   - User query: "Show me ADC studies in breast cancer"
   - AI reasoning (natural, no hardcoding):
     1. Understand: ADC = antibody-drug conjugate
     2. Search titles for: drug names ending in "-mab" + toxin payloads
     3. Search for: "antibody-drug conjugate", "ADC", specific drug names
     4. Cross-reference with breast cancer keywords
   - **This happens naturally with GPT-5's reasoning capability**

**Decision:**
❌ DELETE drug_utils.py entirely
❌ DELETE Drug_Company_names_with_MOA.csv dependency
✅ TRUST AI's pharmaceutical knowledge from training data
✅ LET AI reason about drug classes, abbreviations, novel compounds

---

## AI Reasoning & Model Configuration

### Model Selection: GPT-5 (NOT GPT-4)

**CRITICAL UPDATE:** Forget GPT-4, GPT-4o, GPT-4o-mini — we are now using **GPT-5 model family**

**Primary Model:** `gpt-5-mini` with **high reasoning effort**
- **Reasoning effort:** `high` (for complex multi-step queries)
- **Why:** User queries require logical decomposition
  - Example: "ADCs in breast cancer on 10/18" requires:
    1. Understand request components (drug class, TA, date)
    2. Recognize "ADC" = antibody-drug conjugates (from training data)
    3. Plan filtering strategy (date → TA → drug class keywords)
    4. Execute in optimal order
    5. Present findings with context

**Alternative Architecture (Optional):**
`gpt-5-nano` for routing → `gpt-5-mini` for execution
- **Pros:**
  - Faster response for simple queries ("What time is session X?")
  - Lower cost for meta-queries ("What can you do?")
  - Nano classifies complexity → routes to appropriate model
- **Cons:**
  - Added complexity (2 API calls instead of 1)
  - Routing logic can fail (misclassification)
  - Minimal cost savings if most queries are complex

**Recommendation:** Start with single `gpt-5-mini` approach for simplicity
- Simpler architecture (fewer moving parts)
- Consistent response quality
- Easy to add routing later if needed

### AI's Internal Reasoning Process (What We Enable)

**Example Query:** "What are the sessions on ADCs in breast cancer on 10/18"

**AI's logical thinking (happens naturally with high reasoning effort):**
```
User wants: [studies/sessions]
About: [antibody-drug conjugates - Drug class]
In: [breast cancer - TA]
On: [10/18 - date]

My drug knowledge (from training, NOT hardcoded):
- ADC = antibody-drug conjugate
- Look for: "-mab" suffix drugs with cytotoxic payloads
- Common ADCs: enfortumab vedotin, sacituzumab govitecan, trastuzumab deruxtecan
- Also search: "antibody-drug conjugate", "ADC" in titles

My strategy to narrow from 4,600 studies:
1. Filter by date: 10/18 → ~800 studies remain
2. Filter by therapeutic area: breast cancer → ~150 studies remain
3. Search titles/themes for ADC-related terms → ~20 studies remain
4. Present filtered table + contextual response

Since user asked "what are" (not "tell me about"):
- They want to SEE the studies
- Provide table + brief context
- Offer intelligent follow-ups
```

**This reasoning happens NATURALLY - we don't hardcode the logic!**

---

## Enhanced System Prompt Strategy

```markdown
You are an AI medical affairs intelligence assistant for EMD Serono (Merck KGaA).

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
- 4,686 ESMO 2025 studies/presentations
- Columns: Title, Speakers, Affiliation, Identifier, Date, Time, Session, Theme
- **Important:** Full abstracts NOT yet available (release Oct 13)
- Current data: Titles, authors, institutions, session metadata only

**HOW TO HANDLE QUERIES:**

1. **Decompose requests logically:**
   - Identify what user wants (studies list, summary, rankings, comparisons)
   - Extract filtering criteria (dates, TAs, drugs, institutions)
   - Plan filtering strategy (most restrictive filter first → narrow progressively)

2. **Execute search intelligently:**
   - Apply filters in logical order (date → TA → keywords)
   - Narrow scope to manageable results
   - Think through the filtering before responding

3. **Decide: Show table in chat OR redirect to Data Explorer:**

   **CRITICAL UX DECISION - When to show tables vs. redirect:**

   The AI must reason about whether showing a table adds value or creates redundancy.

   **SHOW TABLE IN CHAT when:**
   - **Contextual analysis queries** (drug/institution/speaker/TA-specific)
     - "What is pembrolizumab?" → Answer + table of pembro studies
     - "What's MD Anderson presenting?" → Answer + table of MD Anderson studies
     - "Tell me about Dr. Smith" → Answer + table of Dr. Smith's presentations
     - "Show me ADC studies in breast cancer" → Table of filtered results + analysis

   - **Multi-dimensional queries** (combined filters producing focused results)
     - "Pembrolizumab studies at MD Anderson" → ~10-30 studies, show table
     - "Bladder cancer immunotherapy combinations" → Specific subset, show table

   - **Analytical queries requiring data reference**
     - User asks for comparison, ranking, trends → Need table to support analysis

   **HANDLE LARGE RESULT SETS:**
   - If >500 studies match → Return first 500 + indicate more available
   - Example: "Showing first 500 of 1,247 bladder cancer studies. Ask me to narrow by date, drug, or institution for more focused results."
   - Let user refine query conversationally rather than redirecting away

   **THE AI DECIDES - NO HARDCODED RULES!**

   Example AI reasoning (happens naturally):
   ```
   User: "What sessions are happening on 10/19?"

   AI thinks:
   - This is a date filter query
   - Result: 847 studies
   - I already filtered the data to count them
   - That filtered dataset is in memory
   - Returning it costs nothing
   - BUT 847 rows might be too many for UI performance
   → DECISION: Return first 500 + offer refinement

   Response: "There are 847 sessions on October 19th. Here are the first 500:

   [TABLE: First 500 studies from 10/19]

   To narrow these down, I can filter by therapeutic area, session type,
   or specific topics. What would you like to focus on?"
   ```

   ```
   User: "What is pembrolizumab's mechanism of action?"

   AI thinks:
   - User wants drug information (factual)
   - BUT they're at a conference intelligence app
   - Showing pembro studies provides context
   - 127 studies (manageable size)
   → DECISION: Answer question + show contextual table

   Response: "Pembrolizumab (Keytruda) is a PD-1 checkpoint inhibitor that
   blocks the PD-1/PD-L1 interaction, allowing T-cells to attack cancer cells...

   [TABLE: 127 pembrolizumab studies]

   The table above shows all pembrolizumab research being presented at ESMO 2025."
   ```

4. **Offer intelligent follow-ups naturally:**
   - Don't force rigid "Would you like me to..." templates
   - Let AI decide contextually appropriate next steps
   - Examples:
     - After showing competitive landscape → "I can deep-dive into any of these mechanisms"
     - After institution analysis → "Want to see collaboration patterns?"
     - After drug query → "Should I compare to Bavencio's positioning?"
   - **Keep it natural and conversational, not scripted**

5. **Response style guidelines:**
   - Concise for "show me" queries (table + context)
   - Analytical for "tell me about" queries (synthesis + insights)
   - Always cite specific Identifiers
   - Admit limitations: "Based on titles only until abstracts available"

6. **Clarification:**
   - Only ask if genuinely ambiguous
   - Use context to make reasonable assumptions
   - Example: "bladder studies" → Assume urothelial carcinoma

**TECHNICAL IMPLEMENTATION NOTE:**
The AI receives instructions to return responses in this format:
```json
{
  "response": "Natural language answer...",
  "table_data": [...],  // If AI decides table is appropriate
  "redirect_to_explorer": {  // If AI decides to redirect
    "message": "To browse all 847 sessions...",
    "filters": ["10/19"],
    "search_query": null
  }
}
```

The AI decides which fields to populate based on query reasoning.

**CRITICAL RULES:**
- Never hallucinate study details
- Always cite Identifier when referencing studies
- If 0 results → Explain and suggest alternatives
- If >100 results → Summarize themes, don't list all
- Acknowledge when full abstracts would provide more detail

**EXAMPLE RESPONSE:**

Query: "What are the sessions on ADCs in breast cancer on 10/18?"

Response:
"Found 18 ADC studies in breast cancer on October 18th:

[Table with 18 studies]

Key observations from titles:
- 12 HER2-targeted ADCs (trastuzumab deruxtecan, T-DXd)
- 4 TROP2-targeted ADCs (sacituzumab govitecan, datopotamab deruxtecan)
- 2 novel targets (AXL, B7-H3)

Session distribution: 12 posters, 4 proffered papers, 2 mini-orals

**What would you like me to do next?**
- Analyze themes across these ADC studies?
- Identify high-priority studies for review?
- Highlight key opinion leaders presenting?
- Map institutional landscape?"

```

---

## Intelligent Follow-Up System

**The AI offers contextual follow-ups based on:**

1. **Query type** (show/list vs. analyze vs. compare)
2. **Result count** (few studies vs. many)
3. **Data availability** (titles only vs. full abstracts when available)
4. **Strategic context** (competitive implications for EMD Serono/Bavencio)

**Standard follow-up menu (AI decides which to offer):**
- Analyze themes across studies?
- Identify high-priority studies for review?
- Map KOL/institution landscape?
- Compare to Bavencio positioning? (when relevant to bladder/RCC)
- Deep-dive into specific study details? (when abstracts available)
- Summarize efficacy/safety findings? (when abstracts available)

**This intelligence happens NATURALLY through extended thinking - no hardcoded rules!**

---

## Token & Cost Management

**Challenge:** 4,686 studies = ~150K tokens if sent as JSON

**Strategy:**
1. **Pre-filter when obvious**
   - User says "pembrolizumab" → Search for it, send only matching studies
   - User says "10/18" → Filter by date first

2. **Chunking for large queries**
   - If >500 studies match → Send first 500 + summary stats
   - AI acknowledges: "Analyzing 500 most recent of 1,200 total studies"

3. **Single model approach (recommended)**
   - Use GPT-5-mini with high reasoning for all queries
   - Simplicity > premature optimization

4. **Alternative: Routing approach (optional)**
   - GPT-5-nano for simple queries ("What time is KEYNOTE-905?")
   - GPT-5-mini for complex analysis ("Compare checkpoint inhibitor combinations across TAs")
   - Add only if performance/cost becomes issue

---

## Phase Breakdown

### **Phase 1: Create Core AI Assistant Module** ✅
- New file: `ai_assistant.py`
- Functions:
  - `handle_chat_query()` - Main entry point
  - `prepare_dataset_context()` - Format data for AI
  - `stream_ai_response()` - GPT-5 streaming
  - `basic_search()` - Simple text search (optional pre-filtering)
- **NO drug expansion** - AI handles naturally
- Clean, minimal codebase (~200 lines)

### **Phase 2: Update App.py Integration**
- Create new endpoint: `/api/chat/ai-first`
- Keep Data Explorer code UNTOUCHED
- Remove imports of old modules (entity_resolver, query_intelligence, etc.)
- Add import for new ai_assistant module
- Test endpoint

### **Phase 3: Frontend Update**
- Update app.js to call `/api/chat/ai-first`
- Minimal changes - just endpoint switch
- Test UI flow

### **Phase 4: Testing & Validation**
- Test your 10 example queries:
  - "What are the sessions on ADCs in breast cancer on 10/18"
  - "Show me the data updates on EV + P"
  - "Top 20 most active authors"
  - Etc.
- Compare responses to current system
- Adjust system prompt if needed

### **Phase 5: Cleanup & Documentation**
- Archive old modules (don't delete yet)
- Document new architecture
- Create migration guide
- Merge to master when satisfied

---

## Success Metrics

✅ **Fewer files:** 6 modules → 1 module
✅ **Less code:** ~1,500 lines → ~200 lines
✅ **More flexible:** Handles new query types without code changes
✅ **Maintainable:** All logic in one place, easy to understand
✅ **Performant:** Similar or better speed (fewer processing steps)
✅ **Cost-effective:** Token usage controlled by smart pre-filtering
✅ **Future-proof:** No hardcoded drug lists to maintain
✅ **AI-first:** Leverages GPT-5's pharmaceutical knowledge naturally

---

## Risk Mitigation

⚠️ **Token costs might increase**
   - Mitigation: Pre-filter obvious queries, use cheaper models when possible

⚠️ **AI might hallucinate without strict guardrails**
   - Mitigation: Always return real table data, system prompt emphasizes grounding

⚠️ **Response quality depends on AI model**
   - Mitigation: Use GPT-5-mini with high reasoning, adjust system prompt based on results

⚠️ **AI might not know extremely novel development codes**
   - Mitigation: Conference data includes drug names in titles/metadata - AI uses context clues

---

## Key Architectural Decisions (The Bible)

**This section documents critical decisions to prevent future drift from vision:**

1. **AI-First Philosophy**
   - Let AI handle understanding, classification, reasoning
   - No rigid pattern matching or intent classification
   - Trust GPT-5's training knowledge over hardcoded rules

2. **No Drug Expansion Module**
   - AI knows drug nomenclature from training data
   - Can infer drug classes from naming patterns
   - Handles novel compounds better than hardcoded CSV
   - **User's reasoning:** "AI's training data >>> our Excel list"

3. **GPT-5 Model Family**
   - Use GPT-5-mini with high reasoning effort
   - NOT GPT-4o, GPT-4o-mini, or older models
   - Optional: Add GPT-5-nano routing later if needed

4. **Minimal Hardcoding**
   - Only provide: UI filters, basic search, table generation
   - Everything else → AI handles naturally
   - Code reduction: ~1,500 lines → ~200 lines

5. **Data Grounding**
   - Always return real CSV data for table display
   - Prevents AI hallucinations
   - AI cites specific study identifiers

6. **Table Display Philosophy: Show the Work**
   - **Critical insight:** If AI already filtered the data to answer the query, return that filtered dataset as a table
   - **Why:** AI already did the work - returning results is free, creates context for follow-ups, avoids redundant re-filtering
   - **Example:** "Show me bladder cancer studies" → AI filters 1,247 studies → Return those studies in table (already in memory!)
   - **Performance win:** Filter once (AI) vs. filter twice (AI + user re-filtering in Data Explorer)
   - **Context preservation:** User can ask follow-up "Which of these are ADCs?" and AI operates on already-filtered set
   - **Only skip table if:** Results are truly massive (>500 studies) AND no analysis needed AND would slow down response
   - **But even then:** AI can return first 500 + note "Showing first 500 of 1,247 results"
   - **Implementation:** AI decides naturally based on result size and query context - NO hardcoded rules

7. **Data Explorer Welcome Message (Landing Page)**
   - **Current state:** AI Assistant tab already has warning popup ✓
   - **Add to Data Explorer tab:** First-time welcome message explaining powerful features
   - **Purpose:** Educate users on advanced search capabilities, guide simple filtering here vs. AI
   - **Message content:**
     - Lightning-fast filtering by date, TA, session type
     - Advanced search: Boolean logic (AND, OR, NOT), exact phrase matching with quotes
     - When to use Data Explorer vs. AI Assistant
   - **Example messaging:**
     ```
     💡 Welcome to Data Explorer

     Lightning-fast filtering and search across all 4,686 ESMO 2025 studies:

     • Filters: Date, Therapeutic Area, Session Type, Theme
     • Search: Boolean logic (AND, OR, NOT) - e.g., "pembrolizumab AND melanoma"
     • Exact Match: Use quotes - e.g., "KEYNOTE-905"
     • Export: Download filtered results as CSV

     Need analysis or competitive insights? Switch to AI Assistant tab for targeted questions.
     ```
   - **Implementation:** One-time dismissible modal on first Data Explorer visit (localStorage flag)

**Refer back to this section whenever tempted to add "helpful" hardcoded logic!**

---

**Next Step:** Phase 1 implementation details in PHASE_1_DETAILS.md
