# COSMIC App - Pre-ESMO Integration Backup Documentation

**Date**: September 25, 2025
**Version**: v18 (Pre-ESMO Integration)
**Status**: Production-ready, deployed on Railway

## Current Working State

### Application Overview
- **Name**: COSMIC (Conference Intelligence App)
- **Purpose**: Medical affairs conference intelligence platform for EMD Serono
- **Current Data**: ASCO GU 2025 conference presentations
- **Deployment**: Live on Railway platform via GitHub integration
- **Status**: Fully functional and running flawlessly

### Key Features (Current)
1. **AI-Powered Analysis**: GPT-4o integration for intelligent query processing
2. **Quick Intelligence Buttons**:
   - 🏆 Competitor Intelligence
   - 👥 KOL Analysis
   - 🏥 Institution Analysis
   - 🧭 Insights & Trends
   - 📋 Strategic Recommendations
3. **Dual-Tab Interface**: Data Explorer + AI Assistant
4. **Real-time Streaming**: Server-sent events for live AI responses
5. **Export Functionality**: CSV/Excel data export
6. **ChromaDB Integration**: Vector database for semantic search

### Technical Stack
- **Backend**: Flask, OpenAI GPT-4o, ChromaDB, Pandas
- **Frontend**: Bootstrap, JavaScript, Server-Sent Events
- **Database**: ChromaDB for vector storage
- **Deployment**: Railway with GitHub integration
- **Data Format**: CSV (ASCO GU 2025 structure)

### Current Data Structure (ASCO)
```
Columns: Abstract #, Poster #, Title, Authors, Institutions
Focus: Bladder cancer, avelumab positioning vs EV+P
Geography: EMD Serono (US/Canada) context
```

## Backup Files Created

### Core Application Files
- ✅ `app_v18_backup_before_esmo_integration.py` - Main Flask application
- ✅ `requirements_v18_backup.txt` - Python dependencies
- ✅ `templates_backup/index_v18_before_esmo.html` - Main UI template
- ✅ `static_backup/styles_v18_before_esmo.css` - Styling
- ✅ `static_backup/app_v18_before_esmo.js` - Frontend JavaScript

### Data Files (Preserved)
- `ASCO GU 2025 Poster Author Affiliations info.csv` - Original dataset
- `Drug_Company_names.csv` - Company mapping data

### Configuration Files
- `Procfile` - Railway deployment configuration
- `.env` - Environment variables (OpenAI API key)

## Rollback Instructions

### If ESMO Integration Fails
1. **Restore Main App**:
   ```bash
   cp app_v18_backup_before_esmo_integration.py app.py
   ```

2. **Restore Templates**:
   ```bash
   cp templates_backup/index_v18_before_esmo.html templates/index.html
   ```

3. **Restore Static Files**:
   ```bash
   cp static_backup/styles_v18_before_esmo.css static/css/styles.css
   cp static_backup/app_v18_before_esmo.js static/js/app.js
   ```

4. **Restore Requirements**:
   ```bash
   cp requirements_v18_backup.txt requirements.txt
   ```

5. **Redeploy to Railway**:
   - Commit restored files to GitHub
   - Railway will auto-deploy the working version

## ESMO Integration Plan Summary

### Planned Changes
1. **Multi-Conference Support**: Toggle between ASCO and ESMO data
2. **Enhanced Data Structure**: Support ESMO's additional metadata
3. **Geographic Context**: EMD Serono (US/Canada) vs Merck KGaA (Global)
4. **Broader Portfolio**: Add CRC/H&N (Erbitux) coverage
5. **Single-Speaker Analysis**: Adapt for ESMO's data limitations

### Implementation Phases
- **Phase 1**: Conference selection UI and infrastructure
- **Phase 2**: Data harmonization and dual CSV support
- **Phase 3**: AI adaptation for conference-specific analysis
- **Phase 4**: UI/UX enhancement for multi-conference experience
- **Phase 5**: Production deployment and optimization

## Critical Notes for Rollback

### Working Features to Preserve
- ✅ All 5 intelligence buttons working perfectly
- ✅ Real-time AI streaming with heartbeat mechanism
- ✅ Export functionality (CSV/Excel)
- ✅ ChromaDB vector search
- ✅ Session-based state management
- ✅ Responsive UI design
- ✅ EMD Serono strategic context

### Dependencies to Maintain
```
Flask==3.0.3
openai==1.51.0
pandas==2.2.3
chromadb==0.5.0
python-dotenv==1.0.1
beautifulsoup4==4.12.3
```

### Railway Deployment Settings
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python app.py`
- **Environment Variables**: `OPENAI_API_KEY` configured
- **GitHub Integration**: Enabled for auto-deployment

## Contact Information
- **Developer**: Claude (Anthropic)
- **User**: m337928 (Medical Affairs)
- **Project**: EMD Serono Conference Intelligence Platform

---

**⚠️ IMPORTANT**: This backup represents the last known working state before ESMO integration. Use these files for emergency rollback if needed.