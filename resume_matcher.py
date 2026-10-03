"""
resume_matcher.py

Phase 3, part 1: resume skill-gap analysis + best-matching postings.

Deliberately built and testable as a standalone script BEFORE any Streamlit
UI exists - same reasoning as every earlier phase: get the logic correct and
verified first, then wire it into a UI. A UI bug and a logic bug look
identical to a user ("wrong numbers on screen"), so untangling them is much
easier if the logic was already proven correct on its own.

WHY THIS REUSES nlp_skill_extractor.extract_skills() INSTEAD OF WRITING A
SEPARATE RESUME PARSER:
    If resume skills and job-posting skills were extracted by two different
    pieces of code, any "gap" this reports would be partly an artifact of
    the two extractors disagreeing with each other, not a real gap between
    what you know and what the market wants. Using the identical extractor
    on both sides means a skill either matches or it doesn't, for one
    consistent reason.
"""

import argparse
import os
import sqlite3
from collections import Counter

from nlp_skill_extractor import extract_skills

DB_PATH = os.path.join(os.path.dirname(__file__), "job_tracker.db")


def extract_text_from_pdf(path: str) -> str:
    """
    Pull raw text out of a PDF resume, page by page.

    WHY pypdf AND NOT SOMETHING FANCIER: it's a pure-Python, no-external-
    dependency PDF text extractor - good enough for a single/double-column
    text resume (the overwhelming majority of student resumes), which is
    all this project needs. It will NOT reliably preserve reading order on
    heavily multi-column or graphically-designed resumes - flagged below as
    a real, known limitation rather than something to discover by surprise.
    """
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text)


def load_resume_text(path: str) -> str:
    """Dispatch by file extension: .pdf gets real PDF extraction, anything else is read as plain text."""
    if path.lower().endswith(".pdf"):
        text = extract_text_from_pdf(path)
        if not text.strip():
            print("WARNING: no text could be extracted from this PDF. It may be a")
            print("scanned image rather than real text - this tool can't read that.")
        return text
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def get_market_skill_frequencies(conn) -> list:
    """
    How often each skill appears across ALL collected postings, most
    common first. This is the "what does the market actually want" signal
    the gap analysis is measured against.
    """
    rows = conn.execute(
        """SELECT s.skill_name, COUNT(*) as freq
           FROM posting_skills ps JOIN skills s ON s.skill_id = ps.skill_id
           GROUP BY s.skill_name
           ORDER BY freq DESC"""
    ).fetchall()
    return rows  # list of (skill_name, freq) tuples


def compute_skill_gap(resume_skills: set, market_freq: list, top_n: int = 15) -> list:
    """
    Of the top_n most in-demand skills in the market, which ones does the
    resume NOT have? Returned in demand order (most in-demand gap first) -
    this is what tells someone what to learn next, prioritized correctly.
    """
    top_market_skills = [name for name, _freq in market_freq[:top_n]]
    return [skill for skill in top_market_skills if skill not in resume_skills]


def get_posting_skill_map(conn) -> dict:
    """job_id -> (title, company, redirect_url, set of skill names) for every posting that has at least one detected skill."""
    rows = conn.execute(
        """SELECT p.job_id, p.title, c.company_name, p.redirect_url, s.skill_name
           FROM postings p
           JOIN posting_skills ps ON p.job_id = ps.job_id
           JOIN skills s ON s.skill_id = ps.skill_id
           LEFT JOIN companies c ON c.company_id = p.company_id"""
    ).fetchall()

    posting_map = {}
    for job_id, title, company, redirect_url, skill_name in rows:
        if job_id not in posting_map:
            posting_map[job_id] = {
                "title": title,
                "company": company,
                "redirect_url": redirect_url,
                "skills": set(),
            }
        posting_map[job_id]["skills"].add(skill_name)
    return posting_map


def find_best_matches(resume_skills: set, posting_map: dict, top_n: int = 10) -> list:
    """
    Rank postings by how many of THEIR required skills the resume already
    covers. Returns (job_id, title, company, overlap_count, matched_skills,
    missing_skills) sorted best-match first.

    Overlap COUNT (not just presence/absence) is deliberate: a posting
    wanting 5 skills where the resume covers 4 is a much stronger match
    than one wanting 5 skills where the resume covers 1 - a plain "does it
    match at all" boolean would treat those identically.
    """
    scored = []
    for job_id, info in posting_map.items():
        posting_skills = info["skills"]
        matched = resume_skills & posting_skills
        missing = posting_skills - resume_skills
        if matched:  # only show postings with at least some real overlap
            scored.append((job_id, info["title"], info["company"], info.get("redirect_url"), len(matched), matched, missing))

    scored.sort(key=lambda x: x[4], reverse=True)

    # Collapse postings that are effectively the same listing (same title,
    # same company, identical required-skill set) - this happens often in
    # practice because recruiters repost the same role to stay visible in
    # search results. Without this, a single repeated listing can crowd out
    # every other genuinely different match in the top N.
    seen_signatures = set()
    deduped = []
    for job_id, title, company, redirect_url, overlap_count, matched, missing in scored:
        signature = (title, company, frozenset(matched | missing))
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        deduped.append((job_id, title, company, redirect_url, overlap_count, matched, missing))

    return deduped[:top_n]


def run(resume_text: str):
    conn = sqlite3.connect(DB_PATH)

    resume_skills = extract_skills(resume_text)
    print(f"Skills detected in resume: {sorted(resume_skills)}\n")

    market_freq = get_market_skill_frequencies(conn)
    gap = compute_skill_gap(resume_skills, market_freq, top_n=15)
    print("--- Skill gap (top 15 in-demand skills you're missing) ---")
    if gap:
        for skill in gap:
            print(f"  {skill}")
    else:
        print("  None — resume covers all top 15 in-demand skills.")

    posting_map = get_posting_skill_map(conn)
    matches = find_best_matches(resume_skills, posting_map, top_n=10)
    print(f"\n--- Top {len(matches)} best-matching postings ---")
    for job_id, title, company, redirect_url, overlap_count, matched, missing in matches:
        print(f"  [{overlap_count} skills matched] {title} @ {company or 'Unknown'}")
        print(f"      matched: {sorted(matched)}")
        print(f"      still missing: {sorted(missing)}")
        if redirect_url:
            print(f"      apply: {redirect_url}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resume skill-gap and job-match analysis.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Path to a resume file (.pdf or .txt)")
    group.add_argument("--text", help="Paste resume text directly as an argument")
    args = parser.parse_args()

    if args.file:
        resume_text = load_resume_text(args.file)
    else:
        resume_text = args.text

    run(resume_text)
