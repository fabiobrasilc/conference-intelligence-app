# Railway Postgres Setup Guide

## Overview

The enrichment cache system now supports **dual-mode operation**:

1. **Production (Railway)**: Postgres metadata + Railway volume storage
2. **Development (local)**: File-based metadata + local directory storage

This setup enables:
- ✅ **Multi-instance safety** - Advisory locks prevent duplicate enrichment
- ✅ **Persistent cache** - Survives deployments via Railway volume
- ✅ **Automatic invalidation** - CSV/model/prompt changes trigger rebuild
- ✅ **Zero-downtime** - Uses fallback data while building cache

---

## Railway Deployment Steps

### Step 1: Add Postgres Service

1. Go to your Railway project dashboard
2. Click **"+ New Service"**
3. Select **"Database" → "Add PostgreSQL"**
4. Railway will automatically:
   - Create the database
   - Inject `DATABASE_URL` environment variable
   - Connect it to your app

### Step 2: Verify Environment Variables

In Railway dashboard, check that these variables are set:

```bash
# Required
OPENAI_API_KEY=sk-proj-...
FLASK_SECRET_KEY=your-secret-key

# Enrichment cache (set to 'true' for production)
ENABLE_AI_ENRICHMENT=true
CACHE_DIR=/app/data

# Auto-injected by Railway when Postgres added
DATABASE_URL=postgresql://postgres:password@postgres.railway.internal:5432/railway
```

### Step 3: Volume Configuration

Your `railway.toml` already has volume configured:

```toml
[[deploy.volumes]]
name = "data"
mountPath = "/app/data"
```

✅ **No changes needed** - volume persists Parquet files across deployments.

### Step 4: Deploy

```bash
# Commit changes
git add .
git commit -m "Add Postgres enrichment cache with advisory locks"
git push origin master

# Railway will auto-deploy
```

### Step 5: Monitor Startup Logs

Watch Railway logs for startup messages:

```
[POSTGRES] Connected to database for enrichment cache
[POSTGRES] Enrichment cache schema ready
[INFO] AI Enrichment: ENABLED (cache dir: /app/data)
[INFO] Postgres cache backend: ENABLED (multi-instance safe)
```

---

## How It Works

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Railway Environment                    │
│                                                           │
│  ┌─────────────────────┐        ┌────────────────────┐  │
│  │   App Instance 1    │        │  App Instance 2    │  │
│  │                     │        │                    │  │
│  │  1. Check Postgres  │◄──────►│  1. Check Postgres │  │
│  │  2. Try lock        │        │  2. Wait if locked │  │
│  │  3. Build cache     │        │  3. Serve fallback │  │
│  │  4. Save to volume  │        │  4. Load when ready│  │
│  └──────────┬──────────┘        └─────────┬──────────┘  │
│             │                              │             │
│             ▼                              ▼             │
│  ┌──────────────────────────────────────────────────┐   │
│  │        Railway Postgres (Metadata)               │   │
│  │  ┌────────────────────────────────────────────┐  │   │
│  │  │  enrichment_cache table                    │  │   │
│  │  │  - csv_hash, model_version, prompt_version │  │   │
│  │  │  - status (building/ready/failed)          │  │   │
│  │  │  - enriched_file_path                      │  │   │
│  │  │  - Advisory locks (pg_try_advisory_lock)   │  │   │
│  │  └────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────┘   │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │        Railway Volume (/app/data)                │   │
│  │  - enriched_{hash}.parquet (Parquet files)      │   │
│  │  - metadata_{hash}.json (File-based backup)     │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### Startup Flow (Multi-Instance Safe)

```python
# Instance 1 (first to start)
1. Compute CSV hash + model/prompt version → dataset_key
2. Query Postgres: SELECT * WHERE csv_hash=... AND status='ready'
3. Not found → Try acquire advisory lock
4. Lock acquired → Mark status='building' in Postgres
5. Start background enrichment (60-90s)
6. Save Parquet to /app/data/enriched_{hash}.parquet
7. Update Postgres: status='ready', file_path='/app/data/...'
8. Release advisory lock

# Instance 2 (starts during Instance 1 build)
1. Compute same dataset_key
2. Query Postgres: status='building' (Instance 1 is working)
3. Try acquire lock → FAILS (Instance 1 holds it)
4. Return None → Serve fallback data (rule-based)
5. Poll Postgres every 5s for status='ready'
6. Once ready, load Parquet from volume

# Instance 3 (starts after build complete)
1. Compute dataset_key
2. Query Postgres: status='ready', file_path='/app/data/...'
3. Load Parquet from volume → Instant startup
```

### Database Schema

Automatically created on first startup:

```sql
CREATE TABLE enrichment_cache (
    id SERIAL PRIMARY KEY,
    csv_hash VARCHAR(64) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    prompt_version VARCHAR(50) NOT NULL,
    enriched_file_path VARCHAR(512),
    status VARCHAR(20) NOT NULL,
    message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (csv_hash, model_version, prompt_version)
);

CREATE INDEX idx_enrichment_lookup
ON enrichment_cache(csv_hash, model_version, prompt_version, status);
```

---

## Local Development

For local development, Postgres is **optional**:

```bash
# .env (local)
ENABLE_AI_ENRICHMENT=false  # Use fast rule-based approach
CACHE_DIR=./data
# DATABASE_URL not set → File-only mode
```

If you want to test Postgres locally:

```bash
# Start local Postgres
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=password postgres:15

# Update .env
DATABASE_URL=postgresql://postgres:password@localhost:5432/postgres
ENABLE_AI_ENRICHMENT=true
```

---

## Monitoring & Debugging

### Check Cache Status in Railway

```bash
# Railway CLI
railway run python -c "
from postgres_cache import PostgresEnrichmentCache
import os

pg = PostgresEnrichmentCache(os.environ['DATABASE_URL'])
record = pg.get_cache_record(
    csv_hash='abc123...',
    model_version='gpt-5-mini',
    prompt_version='v1'
)
print(record)
"
```

### Common Log Messages

**✅ Success:**
```
[POSTGRES] Connected to database for enrichment cache
[POSTGRES] Enrichment cache schema ready
[CACHE] Loading from volume (Postgres-verified): /app/data/enriched_abc123.parquet
[CACHE] Loaded 4686 enriched studies
```

**⚠️ Build in Progress:**
```
[CACHE] Another instance is building, will wait for result...
[CACHE] Enrichment in progress, returning None (use fallback)
```

**🔧 Fallback Mode:**
```
[POSTGRES] Could not connect, falling back to file-based cache
[CACHE] File-only mode (no Postgres)
```

---

## Troubleshooting

### Issue: "No module named 'psycopg2'"

**Solution:** Push with updated requirements.txt (psycopg2-binary==2.9.9 added)

### Issue: "Another instance is building forever"

**Cause:** Instance crashed during build, lock never released

**Solution:** Manually clear stale lock via Railway Postgres console:

```sql
-- Find your lock key (compute from dataset_key)
SELECT pg_advisory_unlock_all();

-- Or reset cache record
UPDATE enrichment_cache
SET status='failed', message='Manual reset'
WHERE status='building';
```

### Issue: Cache not loading after deployment

**Check:**
1. Volume mounted correctly (`mountPath = "/app/data"` in railway.toml)
2. Environment variable `CACHE_DIR=/app/data` set
3. Postgres `enriched_file_path` matches volume path

---

## Performance Expectations

| Scenario | Time | Notes |
|----------|------|-------|
| **Cold start (no cache)** | 60-90s | First instance builds cache in background |
| **Warm start (cache ready)** | <3s | Instant load from Parquet |
| **Multi-instance (building)** | 0s + fallback | Serves rule-based data while waiting |
| **CSV change** | 60-90s | Auto-detects hash change, rebuilds |

---

## Scaling Notes

### Single Instance (1x)
- No concurrency issues
- Advisory locks still beneficial (prevents duplicate work on restart)

### Multiple Instances (2-4x)
- **First instance** acquires lock, builds cache
- **Other instances** use fallback until ready
- **All instances** share cache via volume after build

### High Scale (5+ instances)
- Consider pre-building cache in CI/CD pipeline
- Upload to volume before deployment
- Mark status='ready' in Postgres
- All instances instant-start

---

## Future Enhancements (Optional)

1. **S3/R2 Storage** - Replace volume with object storage for unlimited scale
2. **LISTEN/NOTIFY** - Real-time cache ready notifications (no polling)
3. **Partial TA Caching** - Separate cache files per therapeutic area
4. **Pre-build Pipeline** - GitHub Actions builds cache before deploy

---

## Summary

✅ **Implemented:**
- Postgres metadata storage with advisory locks
- Railway volume for Parquet files
- Automatic schema creation
- Graceful fallback to file-only mode
- Multi-instance coordination

✅ **Production Ready:**
- No git commits of large files
- Survives deployments
- Handles concurrent starts
- Self-healing (automatic rebuilds)

✅ **Developer Friendly:**
- Works locally without Postgres
- Clear logging at every step
- Comprehensive error handling
