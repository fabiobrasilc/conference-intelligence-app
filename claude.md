# COSMIC AI - Conference Intelligence App Documentation

## Project Overview

**COSMIC AI** is a Flask-based pharmaceutical conference intelligence application designed for EMD Serono (Merck KGaA) medical affairs teams. It provides AI-powered analysis of ESMO 2025 conference data across multiple therapeutic areas.

**Primary Use Cases:**
- Conference study search and analysis
- Competitive intelligence reporting
- KOL (Key Opinion Leader) identification
- Strategic briefing generation
- Real-time chat with AI about conference data

---

## Architecture Philosophy: AI-FIRST

**CRITICAL**: This app follows an **AI-FIRST** architecture. Read "The Bible" for full philosophy.

### Core Principles:
1. **Trust AI Intelligence** - Don't hardcode behavior that AI can infer naturally
2. **Minimal Logic** - Let GPT-5 handle drug expansion, keyword extraction, intent detection
3. **Simple Prompts > Complex Code** - Prompt engineering preferred over Python functions
4. **Contextual Understanding** - AI maintains conversation context without scripts

### What This Means:
- NO drug abbreviation expansion dictionaries (AI knows "EV" = enfortumab vedotin)
- NO intent classification functions (AI understands retrieval vs conceptual queries)
- NO hardcoded regex to extract study IDs (AI extracts from conversation naturally)
- YES to clear prompt instructions that leverage AI's training

---

## Project Structure

```
cosmic_mobile/
├── app.py                              # Main Flask application
├── ai_first_refactor/
│   └── ai_assistant.py                 # AI chat logic (AI-first approach)
├── templates/
│   └── index.html                      # Main UI
├── static/
│   ├── css/
│   │   └── styles.css                  # All styles (desktop + mobile)
│   └── js/
│       └── app.js                      # Frontend logic
├── ESMO_2025_FINAL_20251013.csv        # Conference dataset (4,686 studies)
├── bladder-json.json                   # Bladder cancer competitive landscape
├── nsclc-json.json                     # Lung cancer competitive landscape
├── erbi-crc-json.json                  # Colorectal cancer landscape
├── erbi-HN-json.json                   # Head & neck cancer landscape
└── cache/                              # Pre-generated intelligence reports
```

---

## Key Features

### 1. AI Chat Assistant
- **Location**: Chat tab (default view)
- **Scope Options**:
  - All Conference Data (default - 4,686 studies)
  - Therapeutic Area-specific (Bladder, Lung, CRC, H&N, Renal, TGCT, Merkel Cell)
- **Thinking Modes**: Standard (GPT-4o) or Deep (o1-preview for complex analysis)
- **Study List Output**: AI includes formatted study list at end of responses instead of collapsible tables

### 2. Quick Intelligence Buttons
Six pre-built analysis types:
1. **Strategic Briefing** - Comprehensive conference overview
2. **Competitive Intelligence** - Competitor landscape analysis
3. **KOL Insights** - Key opinion leader identification
4. **Pipeline Tracker** - Drug development trends
5. **Data Deep Dive** - Detailed study analysis
6. **Market Dynamics** - Treatment landscape shifts

### 3. Data Explorer
- Searchable table of all conference studies
- Filters: Drug, TA, Session Type, Date
- Mobile: Expandable cards with formatted abstracts
- Desktop: Sortable table with hover tooltips

### 4. Playbook System (Intel Button)
- Generates comprehensive TA-specific reports
- Uses competitive landscape JSON files
- Caches results for performance
- Streaming output for real-time feedback

---

## Technical Stack

### Backend
- **Framework**: Flask
- **AI Models**:
  - GPT-4o (standard thinking)
  - GPT-o1-preview (deep thinking)
  - GPT-5-mini (keyword extraction)
- **Data**: Pandas DataFrames from CSV
- **Streaming**: Server-Sent Events (SSE)

### Frontend
- **UI Framework**: Bootstrap 5.3.3
- **JavaScript**: Vanilla JS (no frameworks)
- **Styling**: CSS custom properties for theming
- **Responsive**: Mobile-first design with media queries

---

## Critical Implementation Details

### 1. AI Chat Flow (ai_first_refactor/ai_assistant.py)

**Two-Step Process:**

#### Step 1: Keyword Extraction (GPT-5-mini)
```python
def extract_keywords_ai(user_query, dataset_size, active_filters, conversation_history):
    # AI extracts structured JSON:
    {
        "drug_combinations": [["enfortumab vedotin", "pembrolizumab"]],
        "institutions": ["Memorial Sloan Kettering"],
        "dates": ["10/18/2025"],  # MUST be MM/DD/YYYY format
        "session_types": ["Poster", "ePoster"],
        "study_identifiers": ["LBA2", "3111eP"],  # NEW: Study IDs
        "search_terms": ["immunotherapy", "bladder cancer"]
    }
```

**CRITICAL Rules:**
- **Date Format**: Dataset uses MM/DD/YYYY - AI converts all dates to this format
- **Study Identifiers**: 3-4 digits + letter (e.g., "LBA2") go in separate field, NOT search_terms
- **Institution Search**: Searches BOTH "Affiliation" AND "Speaker Location" columns
- **Session Types**: Bundles "Poster" and "ePoster" together
- **Continuation Queries**: AI extracts keywords from previous conversation (like "Yes" confirmations)

#### Step 2: Data Filtering + AI Response (GPT-4o/o1-preview)

**Filter Priority (CRITICAL ORDER):**
```python
0. Study Identifiers (HIGHEST - filters Identifier column directly)
1. Dates (MM/DD/YYYY format)
2. Drug Combinations (searches Title, Session, Abstract, Speakers)
3. Institutions (searches Affiliation + Speaker Location)
4. Session Types (searches Session column)
5. General Search Terms (searches Title, Session, search_text)
```

**Why Priority Matters:**
- Study identifiers are unique - should return 1 study per ID
- Drug filters take precedence over general search
- Each filter narrows results sequentially

**AI Response Structure:**
```
1. Answer user's question (70% of response)
   - Use pharmaceutical knowledge
   - Provide strategic context

2. Cite conference evidence (30%)
   - "By the way, X appears in 15 ESMO studies..."
   - Reference specific study Identifiers

3. End with formatted study list (REPLACES TABLE)
   **Relevant studies (ask about specific ones for more details!):**
   - LBA2 - Phase III trial title - Dr. Author
   - 3111eP - Real-world outcomes - Dr. Jones
   ...
```

### 2. Smart TA Scope Detection

**Problem**: Users on "All Conference Data" may get unfocused results.

**Solution**: AI auto-detects scope and adds disclaimers.

```python
# If user has "All Conference Data" selected:

# Case 1: Drug-specific query with clear TA (e.g., "EV+P")
# AI output: "I found 15 bladder cancer studies on EV+P..."
# (Auto-mentions "bladder cancer" explicitly)

# Case 2: Ambiguous query spanning TAs (e.g., "pembrolizumab")
# AI output: "🔍 Scope Note: Searching across all therapeutic areas.
#             Found pembrolizumab studies in lung (127), melanoma (45), bladder (12).
#             Select a TA scope below or refine your query to narrow results."
```

### 3. Mobile UI Considerations

**Chat Input Box**:
```css
/* Mobile only - fixed at bottom */
.ai-chat-input-container {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 1000;
}
```

**Menu Button**:
- Desktop: Three-dot menu button visible
- Mobile: Hidden (no text label creates confusion)

**Data Explorer**:
- Desktop: Sortable table with tooltips
- Mobile: Expandable cards with formatted abstracts

### 4. Abstract Formatting (app.js)

**Problem**: Raw abstracts are wall of text.

**Solution**: Smart section detection with duplicate prevention.

```javascript
function formatAbstract(text) {
  // Detects section headers: Background, Methods, Results, Conclusions
  // Formats with bold + line breaks
  // Prevents duplicates using Set tracking
  // Example output:
  //
  // <strong>Background:</strong><br>
  // Bladder cancer is...
  //
  // <strong>Results:</strong><br>
  // ORR was 68%...
}
```

**Applied To**:
- Mobile card abstracts
- Desktop tooltip abstracts (hover on Data Explorer)

---

## API Endpoints

### Chat Endpoint
```
POST /api/chat/ai-first

Request:
{
  "message": "What are the EV+P studies?",
  "drug_filters": [],
  "ta_filters": ["Bladder Cancer"],
  "session_filters": [],
  "date_filters": [],
  "conversation_history": [...],
  "thinking_mode": "standard" | "deep",
  "active_ta": "Bladder Cancer" (optional),
  "button_type": "insights" (optional)
}

Response: Server-Sent Events (SSE)
data: {"text": "token"}
data: {"text": "token"}
...
data: [DONE]
```

### Playbook Endpoints
```
GET /api/playbook/strategic/stream?ta_filters=Bladder+Cancer
GET /api/playbook/competitor/stream?ta_filters=Bladder+Cancer
GET /api/playbook/kol/stream?ta_filters=Bladder+Cancer
GET /api/playbook/pipeline/stream?ta_filters=Bladder+Cancer
GET /api/playbook/deepdive/stream?ta_filters=Bladder+Cancer
GET /api/playbook/market/stream?ta_filters=Bladder+Cancer
```

---

## Dataset Structure (ESMO_2025_FINAL_20251013.csv)

**Columns:**
- `Identifier` - Study ID (e.g., "LBA2", "3111eP")
- `Title` - Study title
- `Session` - Session name and type
- `Speakers` - Presenting authors
- `Affiliation` - Speaker affiliations
- `Speaker Location` - Geographic location
- `Abstract` - Full abstract text
- `Date` - Presentation date (MM/DD/YYYY)
- `TA` - Therapeutic area
- `search_text` - Concatenated searchable text

**Total**: 4,686 studies

---

## User Workflow

### Default Experience:
1. User lands on Chat tab
2. Scope is pre-set to "All Conference Data"
3. Chat input is enabled immediately
4. Welcome message shows:
   - "Try out the 'Intel' button below to generate comprehensive reports!"
   - "Chat scope is 'all conference data' by default. Select a TA for faster, targeted responses!"

### Chat Interaction:
1. User types query: "What are the EV+P studies?"
2. AI extracts keywords: `drug_combinations: [["enfortumab vedotin", "pembrolizumab"]]`
3. Filters dataset: 118 studies → 15 EV+P studies
4. AI responds with:
   - Strategic analysis of EV+P landscape
   - Key studies cited with Identifiers
   - Formatted study list at end

### Continuation Queries:
1. User asks: "Translate that to French"
2. AI extracts keywords FROM PREVIOUS CONVERSATION (AI-first approach)
3. Same 15 studies maintained
4. Response in French with same study context

### Study-Specific Queries:
1. User asks: "Tell me about LBA2"
2. AI extracts: `study_identifiers: ["LBA2"]`
3. Filters by Identifier column FIRST (highest priority)
4. Returns exactly 1 study
5. AI provides detailed analysis of that study

---

## Common Issues & Solutions

### Issue 1: Continuation Queries Lose Context
**Symptom**: "Translate that to French" returns all studies instead of previous filtered set.

**Solution**: AI extracts keywords from conversation history (prompt instruction, lines 204-213 in ai_assistant.py). NO hardcoded regex needed - trust AI intelligence.

### Issue 2: Study ID Queries Return All Studies
**Symptom**: "Tell me about LBA2" returns 118 studies instead of 1.

**Solution**: Study identifiers go in dedicated field (NOT search_terms) and filter Identifier column FIRST (lines 382-389 in ai_assistant.py).

### Issue 3: Date Filtering Doesn't Work
**Symptom**: "Show me studies from 10/18" returns no results.

**Solution**: Dataset uses MM/DD/YYYY format. AI converts all date formats to MM/DD/YYYY (lines 152-161 in ai_assistant.py).

### Issue 4: Institution Search Misses Results
**Symptom**: "Studies from New York" only shows some results.

**Solution**: Search BOTH "Affiliation" AND "Speaker Location" columns (lines 399-410 in ai_assistant.py).

### Issue 5: Table Expansion Conflicts
**Symptom**: Clicking one table breaks others.

**Solution**: REMOVED collapsible tables entirely. AI now includes formatted study list in text response (lines 770-785 in ai_assistant.py).

---

## Configuration

### Environment Variables (.env)
```
OPENAI_API_KEY=sk-...
```

### Thinking Modes
```python
# Standard thinking: GPT-4o (fast, good for most queries)
thinking_mode = "standard"

# Deep thinking: o1-preview (slower, better for complex strategic analysis)
thinking_mode = "deep"
```

### Chat Scope Default
```javascript
// Default scope in app.js (line 2337)
let activeChatScope = { type: 'all', value: null };

// Dropdown pre-selected to "All Conference Data"
chatScopeDropdown.value = 'all';
```

---

## Deployment

### Local Development
```bash
cd cosmic_mobile
python app.py
# App runs on http://127.0.0.1:5000
```

### Heroku Deployment (mobile branch)
```bash
git push origin mobile
# Auto-deploys to Heroku
```

---

## Key Files to Know

### AI Logic
- **ai_first_refactor/ai_assistant.py** (Lines 120-850)
  - Keyword extraction prompt (lines 144-230)
  - Filtering logic (lines 382-450)
  - AI response generation (lines 651-850)

### Frontend
- **templates/index.html**
  - Welcome message (lines 275-294)
  - Chat scope dropdown (lines 335-345)
  - Quick Intelligence buttons (search for "action-chip")

- **static/js/app.js**
  - Chat scope initialization (lines 2336-2343)
  - Abstract formatting (lines 575-605)
  - Tooltip system (lines 911-952)

- **static/css/styles.css**
  - Mobile chat input (lines 1633-1641)
  - Abstract formatting styles (search for "formatted-abstract")
  - Mobile-specific overrides (lines 2400+)

### Backend
- **app.py**
  - Chat endpoint (lines 4530-4658)
  - Playbook endpoints (search for "@app.route('/api/playbook")
  - Dataset filtering (search for "get_filtered_dataframe_multi")

---

## Design Principles

### UI/UX
- **Mobile-first**: All features work on mobile
- **Minimal chrome**: Clean, uncluttered interface
- **Apple-like**: Subtle shadows, smooth interactions
- **Professional**: Pharmaceutical industry aesthetic

### AI Responses
- **Concise**: Brevity over verbosity
- **Strategic**: Focus on "why it matters"
- **Evidence-based**: Always cite study Identifiers
- **Contextual**: Understand conversation flow

### Code Quality
- **AI-first**: Trust AI intelligence
- **Simple prompts**: Prefer prompt engineering
- **Minimal logic**: Avoid hardcoding
- **Clear comments**: Explain "why" not "what"

---

## Future Considerations

### If You Need to Add Features:

1. **New Filter Type**
   - Add to keyword extraction prompt (ai_assistant.py line 144)
   - Add filtering logic in priority order (ai_assistant.py line 382)
   - Trust AI to extract the keywords naturally

2. **New Intelligence Button**
   - Add button to index.html (copy existing action-chip)
   - Create new playbook endpoint in app.py
   - Use streaming response pattern

3. **New Therapeutic Area**
   - Add to dropdown (index.html line 335)
   - Add TA filter option
   - Create competitive landscape JSON if needed

4. **Modify AI Behavior**
   - Edit PROMPTS, not Python code
   - Trust AI's contextual understanding
   - Test with real queries, iterate prompts

---

## Testing Queries

### Good Test Cases:
```
# Study-specific
"Tell me about LBA2"
"What are the findings from study 3111eP?"

# Drug-specific
"What are the EV+P studies?"
"Show me pembrolizumab data"

# Continuation
User: "Show me EV+P studies"
AI: [Lists 15 studies]
User: "Translate that to French"
AI: [Same 15 studies, in French]

# Institution
"Studies from Memorial Sloan Kettering"
"Which bladder HCPs from New York are presenting?"

# Date
"What's happening on 10/18?"
"Show me studies from October 18th"

# Strategic
"What are the practice-changing studies in bladder cancer?"
"How is the competitive landscape shifting?"
```

---

## Emergency Fixes

### If Chat Stops Working:
1. Check Flask server is running (python app.py)
2. Check OpenAI API key is valid
3. Check browser console for errors
4. Verify dataset CSV is present

### If Filtering Breaks:
1. Check keyword extraction (print statements in ai_assistant.py)
2. Verify filter priority order (lines 382-450)
3. Check dataset column names match code

### If Mobile UI Breaks:
1. Check media queries in styles.css (lines 2400+)
2. Verify fixed positioning for chat input (line 1633)
3. Test in Chrome/Safari DevTools mobile view

---

## Contact & Resources

**GitHub Repo**: https://github.com/fabiobrasilc/conference-intelligence-app
**Branch**: `mobile` (production)

**Key Technologies Documentation**:
- Flask: https://flask.palletsprojects.com/
- OpenAI API: https://platform.openai.com/docs
- Bootstrap 5: https://getbootstrap.com/docs/5.3/

---

## Final Notes

**Remember**: This app is **AI-FIRST**. When in doubt:
- Trust the AI's intelligence
- Simplify prompts instead of adding code
- Let GPT-5 do the heavy lifting
- Keep it clean, keep it simple

The user emphasized this repeatedly: "If I am talking to you now, you understand this entire context windows conversation without a script behind the curtain making you remember what I said..."

That's the philosophy. Apply it everywhere.

---

*Last Updated: 2025-10-17*
*Version: AI-First Refactor (Mobile Branch)*
