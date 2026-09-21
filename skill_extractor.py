"""
skill_extractor.py

Turns raw posting text (title + description) into a list of canonical
skill names, using SKILL_TAXONOMY from skills_taxonomy.py.

Two design choices worth defending in a viva:

1. Word-boundary regex, not substring matching.
   "R" naively substring-matched would match inside "Rider", "HR", "React".
   We use \\b...\\b boundaries and escape special regex characters in each
   alias so multi-word aliases like "power bi" still match correctly.

2. First-match-wins per canonical skill, not per alias.
   A posting might say "Power BI" and "PowerBI" in two different sentences —
   we still want exactly ONE "Power BI" skill attached to that posting, not
   two. So the function returns a set of canonical names, not a list of
   every alias hit.
"""

import re
from skills_taxonomy import SKILL_TAXONOMY


def _build_patterns():
    """Pre-compile one regex per alias, for speed across thousands of postings."""
    patterns = {}
    for canonical_name, aliases in SKILL_TAXONOMY.items():
        compiled = []
        for alias in aliases:
            escaped = re.escape(alias.strip())
            compiled.append(re.compile(r"\b" + escaped + r"\b", re.IGNORECASE))
        patterns[canonical_name] = compiled
    return patterns


_COMPILED_PATTERNS = _build_patterns()


def extract_skills(text: str) -> set:
    """
    Given raw text (e.g. title + ' ' + description), return the set of
    canonical skill names found in it.
    """
    if not text:
        return set()

    found = set()
    for canonical_name, patterns in _COMPILED_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(text):
                found.add(canonical_name)
                break  # no need to check other aliases for this skill
    return found


if __name__ == "__main__":
    # Quick manual sanity check — run `python skill_extractor.py` to eyeball it.
    sample = """
    We are hiring a fresher Data Analyst. Required skills: SQL, Excel,
    Power BI, and basic Python (pandas/numpy). Exposure to Tableau or
    machine learning is a plus. Familiarity with Git and AWS preferred.
    """
    result = extract_skills(sample)
    print(f"Found {len(result)} skills: {sorted(result)}")
