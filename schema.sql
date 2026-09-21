-- schema.sql
-- Fresher Job Market Intelligence Tracker — Phase 1 schema
--
-- Design goal: this schema should NOT need a rewrite when Phase 2 adds
-- recurring/scheduled collection. That's why `search_runs` and the
-- first_seen/last_seen columns exist even though Phase 1 only runs once.

PRAGMA foreign_keys = ON;

-- One row per time you RUN the collector (manually today, via cron/GitHub
-- Actions in Phase 2). This is what lets you later answer "how many fresher
-- data analyst postings existed on 3rd Sept vs 10th Sept" — i.e. trends.
CREATE TABLE IF NOT EXISTS search_runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp   TEXT NOT NULL,              -- ISO8601 UTC, when this run happened
    search_query    TEXT NOT NULL,              -- e.g. "data analyst"
    country         TEXT NOT NULL DEFAULT 'in',
    results_fetched INTEGER DEFAULT 0,
    notes           TEXT
);

-- Normalized out of postings so "TCS" isn't stored as a different string
-- 500 times. Small table, but it matters once you do "top hiring companies"
-- analysis in Phase 3 — you'd be doing fuzzy string grouping otherwise.
CREATE TABLE IF NOT EXISTS companies (
    company_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL UNIQUE
);

-- One row PER UNIQUE JOB POSTING (not per API call, not per run).
-- job_id = Adzuna's own id, used as the natural primary key. This is the
-- single most important design decision in this schema: it's what lets you
-- run the collector every week without creating duplicate rows for postings
-- that are still live from last week.
CREATE TABLE IF NOT EXISTS postings (
    job_id               TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    company_id           INTEGER REFERENCES companies(company_id),
    location_display     TEXT,
    salary_min           REAL,
    salary_max           REAL,
    salary_is_predicted  INTEGER,               -- Adzuna flag: 0 = employer-stated, 1 = modeled
    category_label       TEXT,
    contract_type        TEXT,                  -- permanent / contract
    contract_time        TEXT,                  -- full_time / part_time
    description_snippet  TEXT,
    redirect_url         TEXT,
    created_at_source    TEXT,                  -- date Adzuna says the ad first appeared
    is_fresher_heuristic INTEGER DEFAULT 0,      -- 1 if it passed our fresher/entry-level keyword filter
    first_seen_run_id    INTEGER REFERENCES search_runs(run_id),
    last_seen_run_id     INTEGER REFERENCES search_runs(run_id),
    first_seen_date      TEXT,
    last_seen_date       TEXT                    -- updated every run the posting is still returned by the API
);

-- Master skill vocabulary. skill_category lets you later slice "languages
-- vs tools vs soft skills" in the dashboard without re-parsing text.
CREATE TABLE IF NOT EXISTS skills (
    skill_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name     TEXT NOT NULL UNIQUE,
    skill_category TEXT
);

-- Many-to-many: one posting mentions many skills, one skill appears in many
-- postings. This junction table is what makes trend queries a simple
-- GROUP BY instead of re-scanning description text every time.
CREATE TABLE IF NOT EXISTS posting_skills (
    job_id   TEXT REFERENCES postings(job_id),
    skill_id INTEGER REFERENCES skills(skill_id),
    PRIMARY KEY (job_id, skill_id)
);

CREATE INDEX IF NOT EXISTS idx_postings_created ON postings(created_at_source);
CREATE INDEX IF NOT EXISTS idx_posting_skills_skill ON posting_skills(skill_id);
