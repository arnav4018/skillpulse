"""
fetch_jobs.py

Phase 1 collection script: pulls fresher/entry-level "data analyst" postings
for India from the Adzuna API and stores them in SQLite (job_tracker.db).

Usage:
    python fetch_jobs.py
    python fetch_jobs.py --query "data analyst" --pages 3

Design notes (for your report / viva):

- IDEMPOTENT WRITES: re-running this script does not create duplicate rows.
  Every posting is upserted on job_id (Adzuna's own id). If a posting was
  already in the DB, we just update last_seen_date/last_seen_run_id. This
  is what makes the SAME script usable in Phase 2 for recurring collection —
  you don't need to rewrite the storage logic, only add a scheduler on top.

- RATE LIMIT AWARENESS: Adzuna's free tier is roughly 1,000 calls/month
  (~33/day). Each page of results = 1 call. This script defaults to a small
  number of pages per run and prints how many calls it used, so you don't
  burn the quota accidentally while testing.

- FRESHER FILTERING IS A HEURISTIC, NOT AN API FILTER: Adzuna has no
  "experience level" parameter. We fetch broadly for "data analyst" and then
  flag postings whose title/description contain fresher/entry-level language
  (see FRESHER_KEYWORDS in skills_taxonomy.py). This is a named, documented
  limitation — not hidden. Postings that don't match the heuristic are still
  stored (is_fresher_heuristic = 0) so you don't silently lose data; you
  just filter on that column later in analysis.
"""

import argparse
import os
import sqlite3
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from skills_taxonomy import FRESHER_KEYWORDS
from nlp_skill_extractor import extract_skills

load_dotenv()

APP_ID = os.getenv("ADZUNA_APP_ID")
APP_KEY = os.getenv("ADZUNA_APP_KEY")
COUNTRY = "in"
BASE_URL = f"https://api.adzuna.com/v1/api/jobs/{COUNTRY}/search"
DB_PATH = os.path.join(os.path.dirname(__file__), "job_tracker.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_connection():
    """Open the DB and make sure the schema exists (safe to call every run)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    return conn


def is_fresher_posting(title: str, description: str) -> bool:
    text = f"{title} {description}".lower()
    return any(keyword in text for keyword in FRESHER_KEYWORDS)


def fetch_page(query: str, page: int, results_per_page: int = 50) -> dict:
    """One API call = one page of results. Raises on non-200 so failures aren't silent."""
    url = f"{BASE_URL}/{page}"
    params = {
        "app_id": APP_ID,
        "app_key": APP_KEY,
        "results_per_page": results_per_page,
        "what": query,
        "content-type": "application/json",
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_or_create_company(conn, company_name: str) -> int:
    if not company_name:
        company_name = "Unknown"
    cur = conn.execute(
        "SELECT company_id FROM companies WHERE company_name = ?", (company_name,)
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO companies (company_name) VALUES (?)", (company_name,)
    )
    return cur.lastrowid


def get_or_create_skill(conn, skill_name: str) -> int:
    cur = conn.execute("SELECT skill_id FROM skills WHERE skill_name = ?", (skill_name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO skills (skill_name) VALUES (?)", (skill_name,))
    return cur.lastrowid


def upsert_posting(conn, job: dict, run_id: int, fresher_flag: bool) -> str:
    job_id = str(job.get("id"))
    title = job.get("title", "")
    description = job.get("description", "")
    company_name = job.get("company", {}).get("display_name", "Unknown")
    company_id = get_or_create_company(conn, company_name)
    location = job.get("location", {}).get("display_name", "")
    today = datetime.now(timezone.utc).date().isoformat()

    existing = conn.execute(
        "SELECT job_id FROM postings WHERE job_id = ?", (job_id,)
    ).fetchone()

    if existing:
        # Seen before (e.g. a re-run within the same week): just bump last_seen.
        conn.execute(
            """UPDATE postings
               SET last_seen_run_id = ?, last_seen_date = ?
               WHERE job_id = ?""",
            (run_id, today, job_id),
        )
    else:
        conn.execute(
            """INSERT INTO postings (
                job_id, title, company_id, location_display,
                salary_min, salary_max, salary_is_predicted,
                category_label, contract_type, contract_time,
                description_snippet, redirect_url, created_at_source,
                is_fresher_heuristic, first_seen_run_id, last_seen_run_id,
                first_seen_date, last_seen_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id, title, company_id, location,
                job.get("salary_min"), job.get("salary_max"),
                job.get("salary_is_predicted"),
                job.get("category", {}).get("label"),
                job.get("contract_type"), job.get("contract_time"),
                description, job.get("redirect_url"), job.get("created"),
                1 if fresher_flag else 0,
                run_id, run_id, today, today,
            ),
        )

    # Skill extraction: run on every posting, insert-or-ignore into the
    # junction table (a posting's skills don't change between runs).
    skills_found = extract_skills(f"{title} {description}")
    for skill_name in skills_found:
        skill_id = get_or_create_skill(conn, skill_name)
        conn.execute(
            "INSERT OR IGNORE INTO posting_skills (job_id, skill_id) VALUES (?, ?)",
            (job_id, skill_id),
        )

    return job_id


def run_collection(query: str, pages: int, results_per_page: int):
    if not APP_ID or not APP_KEY:
        raise SystemExit(
            "Missing ADZUNA_APP_ID / ADZUNA_APP_KEY. Copy .env.example to .env "
            "and fill in your credentials from developer.adzuna.com"
        )

    conn = get_connection()
    run_timestamp = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO search_runs (run_timestamp, search_query, country) VALUES (?, ?, ?)",
        (run_timestamp, query, COUNTRY),
    )
    run_id = cur.lastrowid

    total_fetched = 0
    total_fresher = 0
    api_calls_used = 0

    for page in range(1, pages + 1):
        print(f"Fetching page {page}/{pages}...")
        data = fetch_page(query, page, results_per_page)
        api_calls_used += 1
        results = data.get("results", [])
        if not results:
            print("No more results — stopping early.")
            break

        for job in results:
            title = job.get("title", "")
            description = job.get("description", "")
            fresher_flag = is_fresher_posting(title, description)
            upsert_posting(conn, job, run_id, fresher_flag)
            total_fetched += 1
            if fresher_flag:
                total_fresher += 1

        conn.commit()
        time.sleep(1)  # be polite to the API between pages

    conn.execute(
        "UPDATE search_runs SET results_fetched = ? WHERE run_id = ?",
        (total_fetched, run_id),
    )
    conn.commit()
    conn.close()

    print("\n--- Run summary ---")
    print(f"Run ID: {run_id}")
    print(f"API calls used this run: {api_calls_used}")
    print(f"Postings fetched (upserted): {total_fetched}")
    print(f"Postings flagged fresher/entry-level: {total_fresher}")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect fresher job postings from Adzuna.")
    parser.add_argument("--query", default="data analyst", help="Search term (what=)")
    parser.add_argument("--pages", type=int, default=3, help="Number of result pages to fetch (1 page = 1 API call)")
    parser.add_argument("--results-per-page", type=int, default=50, help="Results per page (max ~50)")
    args = parser.parse_args()

    run_collection(args.query, args.pages, args.results_per_page)
