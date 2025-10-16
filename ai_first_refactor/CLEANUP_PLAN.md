# App Cleanup Plan - Remove Legacy AI Code

## Current State Analysis

### Active Endpoints
✅ **USED:** `/api/chat/ai-first` (line 4846) - Our new two-step AI flow
❌ **UNUSED:** `/api/chat/stream` (line 4514) - Old basic chat
❌ **UNUSED:** `/api/chat/enhanced` (line 4666) - Old enhanced search pipeline

**Frontend:** `static/js/app.js` line 1127 calls `/api/chat/ai-first` only

### Legacy Imports (Lines 32-36)
```python
from entity_resolver import expand_query_entities, resolve_drug_name
from improved_search import precompute_search_text, smart_search
from query_intelligence import analyze_query
from enhanced_search import complete_search_pipeline
from lean_synthesis import build_lean_synthesis_prompt, estimate_prompt_tokens
```

**Usage Analysis:**
- `expand_query_entities`: 0 usages ❌ REMOVE
- `resolve_drug_name`: 0 usages ❌ REMOVE
- `smart_search`: 1 usage (in `/api/chat/enhanced`) ❌ REMOVE with endpoint
- `analyze_query`: 0 usages ❌ REMOVE
- `complete_search_pipeline`: 1 usage (in `/api/chat/enhanced`) ❌ REMOVE with endpoint
- `build_lean_synthesis_prompt`: 0 usages ❌ REMOVE
- `estimate_prompt_tokens`: 0 usages ❌ REMOVE
- `precompute_search_text`: USED by ai_assistant.py ✅ KEEP

### Legacy Modules to Archive
These files can be moved to archive folder:

1. ❌ `entity_resolver.py` (415 lines) - Drug expansion dictionaries
2. ❌ `query_intelligence.py` (200 lines) - Intent classification
3. ❌ `enhanced_search.py` (400 lines) - Complex search pipeline
4. ❌ `lean_synthesis.py` (300 lines) - Token optimization
5. ⚠️ `improved_search.py` - PARTIAL (keep `precompute_search_text`, remove `smart_search`)

**Total deletion:** ~1,315 lines of unused code

---

## Cleanup Steps

### Step 1: Remove Unused Endpoints
**File:** `app.py`

**Remove lines 4514-4664:**
```python
@app.route('/api/chat/stream', methods=['POST'])
def stream_chat_api():
    # ... 150 lines ...

@app.route('/api/chat/enhanced', methods=['POST'])
def stream_chat_api_enhanced():
    # ... 180 lines ...
```

**Savings:** ~330 lines

### Step 2: Remove Legacy Imports
**File:** `app.py` lines 32-36

**Remove:**
```python
from entity_resolver import expand_query_entities, resolve_drug_name
from improved_search import precompute_search_text, smart_search
from query_intelligence import analyze_query
from enhanced_search import complete_search_pipeline
from lean_synthesis import build_lean_synthesis_prompt, estimate_prompt_tokens
```

**Replace with:**
```python
from improved_search import precompute_search_text  # Only function we need
```

**Savings:** 4 lines

### Step 3: Archive Legacy Modules
Create `legacy_modules_archived/` folder and move:

```bash
mkdir legacy_modules_archived
mv entity_resolver.py legacy_modules_archived/
mv query_intelligence.py legacy_modules_archived/
mv enhanced_search.py legacy_modules_archived/
mv lean_synthesis.py legacy_modules_archived/
```

**Create archive README:**
```markdown
# Legacy Modules - Archived Oct 2025

These modules were replaced by the AI-first architecture.

Replaced by: ai_first_refactor/ai_assistant.py (2-step AI flow)

- entity_resolver.py: AI now handles drug abbreviations via GPT-5 pharmaceutical knowledge
- query_intelligence.py: AI interprets queries naturally, no intent classification needed
- enhanced_search.py: Replaced by simple pandas filtering after AI keyword extraction
- lean_synthesis.py: GPT-5 handles token optimization, no manual truncation needed
```

### Step 4: Clean improved_search.py
**File:** `improved_search.py`

**Keep:**
- `precompute_search_text()` function (needed by ai_assistant.py)

**Remove:**
- `smart_search()` function (unused)

### Step 5: Verify Frontend Integration
**File:** `static/js/app.js`

✅ **Already correct** - Uses `/api/chat/ai-first` endpoint (line 1127)

**Check for:**
- Table rendering works
- SSE streaming works
- Error handling works

### Step 6: Update Documentation
**Files to update:**

1. `README.md` - Remove references to old modules
2. `ARCHITECTURE_PLAN.md` - Already reflects new architecture
3. Add migration note:
   ```markdown
   ## Migration Note (Oct 2025)
   Migrated from 6-module system (1,500 lines) to AI-first 2-step flow (200 lines).
   Legacy modules archived in legacy_modules_archived/
   ```

---

## Testing Checklist

After cleanup, test these scenarios:

### Backend Tests
- [ ] Flask server starts without import errors
- [ ] `/api/chat/ai-first` endpoint responds
- [ ] GPT-5 keyword extraction works
- [ ] DataFrame filtering works
- [ ] Table generation works (≤500 studies)
- [ ] AI response streaming works

### Frontend Tests
- [ ] Chat interface loads
- [ ] User can send messages
- [ ] "Thinking..." indicator shows
- [ ] Table renders in Data Explorer tab
- [ ] AI response streams token-by-token
- [ ] Markdown rendering works
- [ ] Error handling shows user-friendly messages

### Integration Tests
- [ ] "EV + P" query returns 11 studies
- [ ] "nivolumab renal cancer 10/18" returns 6 studies
- [ ] "MD Anderson" query returns 73 studies
- [ ] AI shows transparency: "I found X studies on **date** about **drug**..."

---

## Risk Mitigation

### Backup Before Cleanup
```bash
# Create backup
cp app.py app_backup_pre_cleanup_$(date +%Y%m%d).py

# Or full project backup
cd ..
tar -czf conference_intelligence_app_backup_$(date +%Y%m%d).tar.gz conference_intelligence_app/
```

### Rollback Plan
If issues arise:
1. Restore `app.py` from backup
2. Move modules back from `legacy_modules_archived/`
3. Restore imports

### Gradual Approach (If Preferred)
Instead of deleting, comment out first:

```python
# DEPRECATED - Replaced by /api/chat/ai-first
# @app.route('/api/chat/stream', methods=['POST'])
# def stream_chat_api():
#     ...
```

Keep for 1-2 weeks, then delete if no issues.

---

## Expected Outcomes

### Before Cleanup
- **app.py:** ~5,000 lines
- **Modules:** 6 files, ~1,500 lines
- **Total:** ~6,500 lines

### After Cleanup
- **app.py:** ~4,670 lines (remove 330 lines of unused endpoints)
- **Modules:** 2 files (improved_search.py, ai_assistant.py)
- **Archived:** 4 files in legacy_modules_archived/
- **Total active code:** ~4,900 lines

**Reduction:** 1,600 lines (~25% code reduction)

### Performance Improvements
- ✅ Fewer imports = faster startup
- ✅ No unused module loading
- ✅ Simpler code path = easier debugging
- ✅ AI-first = more accurate results

---

## Files to Modify

| File | Action | Lines Changed |
|------|--------|---------------|
| app.py | Remove 2 endpoints, clean imports | -334 |
| improved_search.py | Remove smart_search() | ~-100 |
| entity_resolver.py | Archive | 0 (move file) |
| query_intelligence.py | Archive | 0 (move file) |
| enhanced_search.py | Archive | 0 (move file) |
| lean_synthesis.py | Archive | 0 (move file) |

**Total:** ~434 lines deleted, 4 files archived

---

## Implementation Order

1. ✅ Create backup
2. ✅ Create `legacy_modules_archived/` folder
3. ✅ Remove unused endpoints from app.py
4. ✅ Clean up imports in app.py
5. ✅ Move modules to archive
6. ✅ Test Flask server starts
7. ✅ Test /api/chat/ai-first endpoint
8. ✅ Test frontend chat interface
9. ✅ Run validation queries
10. ✅ Update documentation

**Estimated Time:** 30 minutes
**Risk Level:** Low (frontend already using new endpoint)
