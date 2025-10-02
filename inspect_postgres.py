"""
Inspect Postgres Enrichment Cache Metadata
Shows cache status from Railway Postgres database
"""

import os
import sys
from dotenv import load_dotenv

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL not set")
    print("This script must run on Railway or with DATABASE_URL configured in .env")
    exit(1)

try:
    import psycopg2
except ImportError:
    print("❌ psycopg2 not installed")
    print("Run: pip install psycopg2-binary")
    exit(1)

print("=" * 80)
print("📊 Postgres Enrichment Cache Metadata")
print("=" * 80)

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Get all cache records
    cur.execute("""
        SELECT
            csv_hash,
            model_version,
            prompt_version,
            status,
            enriched_file_path,
            message,
            created_at,
            updated_at
        FROM enrichment_cache
        ORDER BY updated_at DESC
    """)

    rows = cur.fetchall()

    if not rows:
        print("\n⚠️  No cache records found in database")
        print("Cache table exists but is empty")
    else:
        print(f"\n✅ Found {len(rows)} cache record(s)\n")

        for row in rows:
            csv_hash, model, prompt, status, file_path, message, created, updated = row

            print("-" * 80)
            print(f"  CSV Hash: {csv_hash[:16]}...")
            print(f"  Model: {model}")
            print(f"  Prompt Version: {prompt}")
            print(f"  Status: {status}")
            print(f"  File Path: {file_path}")
            if message:
                print(f"  Message: {message}")
            print(f"  Created: {created}")
            print(f"  Updated: {updated}")

    cur.close()
    conn.close()

    print("\n" + "=" * 80)
    print("✅ Inspection complete!")

except Exception as e:
    print(f"\n❌ Error connecting to Postgres: {e}")
    exit(1)
