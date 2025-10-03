import os, urllib.parse as up, pg8000

url = up.urlparse(os.environ["postgresql://postgres:QmIGCYgqJojGsDVfcnBqKdFAyKFqZIXm@postgres.railway.internal:5432/railway"])
params = {}
if url.query and "sslmode=require" in url.query:
    params["ssl"] = {"sslmode": "require"}

conn = pg8000.connect(
    user=url.username,
    password=url.password,
    host=url.hostname,
    port=url.port or 5432,
    database=url.path.lstrip("/"),
    **params
)
cur = conn.cursor()
cur.execute("""SELECT csv_hash, model_version, prompt_version, status,
                      enriched_file_path, updated_at
               FROM enrichment_cache
               ORDER BY updated_at DESC
               LIMIT 10""")
for row in cur.fetchall():
    print(row)
cur.close(); conn.close()
