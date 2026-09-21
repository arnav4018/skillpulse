# SkillPulse — Phase 1

Fresher Job Market Intelligence & Skill-Trend Tracker.
Phase 1: one-time collection of fresher/entry-level Data Analyst postings
(India, via Adzuna API), stored in SQLite, with taxonomy-based skill extraction.

## Setup

1. Create and activate a virtual environment:
   ```
   python3 -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Get Adzuna API credentials at https://developer.adzuna.com and copy them in:
   ```
   cp .env.example .env
   # then edit .env and paste your real ADZUNA_APP_ID / ADZUNA_APP_KEY
   ```
4. Run the collector:
   ```
   python fetch_jobs.py --query "data analyst" --pages 3
   ```
5. Inspect the result:
   ```
   sqlite3 job_tracker.db
   sqlite> SELECT COUNT(*) FROM postings;
   sqlite> .quit
   ```

## Files

- `schema.sql` — database structure (auto-applied on every run, safe to re-run)
- `skills_taxonomy.py` — the skill dictionary + fresher-keyword list
- `skill_extractor.py` — regex matching logic that reads the taxonomy
- `fetch_jobs.py` — main script: calls Adzuna, writes to SQLite
- `job_tracker.db` — created after your first run (not committed to git)
- `SkillPulse_Phase1_Guide.pdf` — concept guide (what/how/why + learning topics)

## Re-running

Safe to run multiple times — postings are upserted on Adzuna's job ID, so
re-running does not create duplicates; it only updates `last_seen_date` on
postings still returned by the API.
