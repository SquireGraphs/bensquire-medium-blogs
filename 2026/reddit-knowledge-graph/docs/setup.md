# Detailed Setup Guide

## Step 1 — Reddit API credentials

1. Log in to Reddit and go to https://www.reddit.com/prefs/apps
2. Click **"create another app..."** at the bottom
3. Fill in:
   - **Name**: `reddit-knowledge-graph` (or any name)
   - **Type**: Select **script**
   - **redirect uri**: `http://localhost:8080` (placeholder — not used)
4. Click **Create app**
5. Copy the values:
   - `client_id`: The string shown **under the app name** (looks like `abc123xyz`)
   - `client_secret`: The value next to **"secret"**

Using your Reddit `username` and `password` in `.env` is optional but **strongly recommended** — it raises your rate limit from 10 to 60 requests/minute.

---

## Step 2 — Anthropic API key

1. Go to https://console.anthropic.com/settings/keys
2. Click **"Create Key"**
3. Copy the key (starts with `sk-ant-...`)

**Model selection**: The default is `claude-3-5-haiku-20241022` which is fast and cost-effective. For higher extraction quality, use `claude-3-5-sonnet-20241022` (note: ~8x higher cost).

---

## Step 3 — Python environment

```bash
# Requires Python 3.11+
python --version

# Create virtual environment
python -m venv .venv

# Activate
source .venv/bin/activate          # Mac/Linux
.venv\Scripts\activate             # Windows

# Install dependencies
pip install -r requirements.txt

# Or install as a package (enables `rkgraph-*` CLI commands)
pip install -e .
```

---

## Step 4 — Configure .env

```bash
cp .env.example .env
```

Open `.env` in your editor and fill in at minimum:

```env
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_secret_here
REDDIT_USER_AGENT=reddit-knowledge-graph/0.1 by u/your_username
REDDIT_USERNAME=your_username          # Optional but recommended
REDDIT_PASSWORD=your_password          # Optional but recommended

ANTHROPIC_API_KEY=sk-ant-...
```

---

## Step 5 — Start Neo4j

```bash
docker compose up -d
```

This starts Neo4j 5.x Community with the APOC and Graph Data Science plugins.

Verify it's running:
```bash
docker ps
# Should show reddit_kg_neo4j as running

# Or open in browser:
open http://localhost:7474
```

Neo4j Browser credentials: `neo4j` / `password123` (matches `.env` defaults).

---

## Step 6 — Initialise schema

```bash
python scripts/setup_schema.py
```

Expected output:
```
✓ Connected to Neo4j

Applying schema...
✓ Schema applied successfully
```

This is idempotent — safe to run again at any time.

---

## Step 7 — Test with a dry run

Before spending API credits on a full scrape, verify your Reddit credentials work:

```bash
python scripts/run_pipeline.py --dry-run --subreddit neo4j
```

This scrapes r/neo4j, enriches the first 3 posts with Claude, and prints the extracted entities and sentiment without writing anything to Neo4j.

---

## Step 8 — Run the pipeline

```bash
# Start with one subreddit to verify end-to-end
python scripts/run_pipeline.py --subreddit neo4j

# Then run all subreddits (this will take 30-60 minutes for a full 3-year backfill)
python scripts/run_pipeline.py
```

Monitor progress via the Rich progress bar in the terminal.

---

## Step 9 — Query the agent

```bash
python scripts/run_agent.py
```

Type a question at the prompt:
```
You: Where are people talking about Neo4j the most?

Agent: Based on the knowledge graph, Neo4j is discussed most in:
1. r/neo4j (as expected) — 1,234 posts
2. r/knowledgegraph — 456 posts
3. r/dataengineering — 234 posts
...
```

---

## Incremental updates

To keep the graph fresh, run the pipeline on a schedule:

```bash
# Run daily via cron (add to crontab -e):
0 6 * * * cd /path/to/repo && .venv/bin/python scripts/run_pipeline.py --no-schema

# Or use the APScheduler-based scheduler:
python -c "
from apscheduler.schedulers.blocking import BlockingScheduler
from src.pipeline.orchestrator import Pipeline

scheduler = BlockingScheduler()
scheduler.add_job(Pipeline().run, 'cron', hour=6)
scheduler.start()
"
```

---

## Troubleshooting

### "prawcore.exceptions.ResponseException: received 401 HTTP response"
Your Reddit credentials are wrong. Double-check `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_USER_AGENT` in `.env`.

### "anthropic.AuthenticationError"
Your `ANTHROPIC_API_KEY` is missing or invalid.

### "ServiceUnavailable: Connection refused on port 7687"
Neo4j isn't running. Run `docker compose up -d` and wait ~30 seconds.

### "neo4j.exceptions.ConstraintError"
Usually happens if you try to run `setup_schema.py` twice without `IF NOT EXISTS` — but all our DDL includes `IF NOT EXISTS`, so this shouldn't occur. If it does, try `python scripts/setup_schema.py --drop` followed by a fresh `setup_schema.py`.

### Posts not found / empty scrape results
- Verify your keywords in `FILTER_KEYWORDS` are spelled correctly.
- Check `LOOKBACK_MONTHS` — older posts may have been deleted by Reddit.
- Reddit's API only surfaces the ~1,000 most recent posts per subreddit via `.new()`. Older posts require Pushshift/Arctic Shift.
