# Code Cleanup Plan for Conference Intelligence App

## Current State
- **Total lines**: 4,993
- **Target**: ~2,500-3,000 lines (remove ~40-50% bloat)

## Items to Remove

### 1. ASCO GU References (13 occurrences)
- Line 234: ConferenceConfig comment
- Lines 266-287: Entire ASCO_GU_2025 conference config block
- Lines 1328, 1371, 1430: ASCO GU in AI prompts
- Line 2535: ASCO GU in context description
- Lines 3775, 4476, 5444: ASCO GU in responses
- Line 5969: Excel sheet name

**Action**: Remove all ASCO GU config and replace references with "ESMO 2025"

### 2. Duplicate/Legacy Filtering Functions

#### REMOVE:
- `get_filtered_dataframe()` (line 514-581) - OLD single-filter version
- `get_filter_context()` (line 585-596) - OLD single-filter context
- Any code paths that still call the old single-filter functions

#### KEEP:
- `get_filtered_dataframe_multi()` (line 912) ✅
- `get_filter_context_multi()` (line 996) ✅
- All specific TA filter functions (bladder, renal, lung, etc.) ✅

### 3. Conference Data Model (Lines 227-315)
The entire `ConferenceConfig` dataclass and `get_conference_configs()` function appears to be for supporting multiple conferences.

**Decision**: Since we only support ESMO 2025, **REMOVE** all of this abstraction:
- ConferenceConfig dataclass (lines 227-257)
- get_conference_configs() function (lines 259-315)

### 4. Legacy AI/Chat Functions (if not used)

Need to check if these are still called:
- `legacy_chat_handler()` (line 5746)
- Old routing logic
- Unused helper functions

### 5. Unused Helper Functions

Functions that may not be called anywhere:
- `debug_filter()` (line 4027) - check if this is a debug endpoint
- Old institution normalization code if duplicated

## Cleanup Steps

1. **Backup current app.py** → `app_before_cleanup.py`
2. **Remove ASCO GU** config and references
3. **Remove ConferenceConfig** abstraction (ESMO-only now)
4. **Remove old single-filter functions** (`get_filtered_dataframe`, `get_filter_context`)
5. **Verify all routes use multi-filter functions**
6. **Remove legacy chat handler** if unused
7. **Clean up imports** and dead code
8. **Test everything still works**

## Expected Result
- **Before**: 4,993 lines
- **After**: ~2,500-3,000 lines
- **All functionality preserved**, just cleaner code
