"""
nlp_skill_extractor.py

Phase 2 upgrade: same skill vocabulary as Phase 1 (SKILL_TAXONOMY), but matched
using spaCy's PhraseMatcher instead of hand-rolled regex.

WHY THIS IS AN UPGRADE, NOT JUST A DIFFERENT WAY TO DO THE SAME THING:

1. Tokenization-based matching instead of character-based matching.
   Regex works on raw characters, which is why Phase 1 needed manual \\b
   word-boundary tricks and re.escape() to avoid "R" matching inside
   "Director". spaCy first splits text into tokens (words), and PhraseMatcher
   matches sequences of TOKENS, not substrings. "R" as a token is never part
   of the token "Director" - so the boundary problem is solved structurally,
   not by a workaround.

2. attr="LOWER" gives case-insensitivity without needing re.IGNORECASE
   scattered through pattern construction - it's a property of how the
   matcher compares tokens, set once.

3. Easier to extend later (Phase 3 territory, not needed now): spaCy's
   pipeline can add lemmatization ("running" -> "run") or part-of-speech
   filtering on top of this same matcher object if you ever need it -
   regex has no equivalent extension path.

WHAT THIS DOES NOT FIX (be honest about this in your report):
   This still only finds skills that are IN SKILL_TAXONOMY. Swapping the
   matching engine does not discover new skills by itself - that requires
   either a bigger curated vocabulary (Part 2 of the upgrade) or a different
   technique entirely (full NER, out of scope for this project's budget).

WHY spacy.blank("en") AND NOT a downloaded model (en_core_web_sm):
   PhraseMatcher only needs tokenization to work - it doesn't need the part-
   of-speech tagger, parser, or word vectors that come with a full trained
   model. spacy.blank("en") gives just the tokenizer, loads instantly, and
   needs no separate model download. Using a full model here would be
   heavier for zero benefit to this specific task.
"""

import spacy
from spacy.matcher import PhraseMatcher
from skills_taxonomy import SKILL_TAXONOMY

_nlp = spacy.blank("en")
_matcher = PhraseMatcher(_nlp.vocab, attr="LOWER")

for canonical_name, aliases in SKILL_TAXONOMY.items():
    patterns = [_nlp.make_doc(alias) for alias in aliases]
    _matcher.add(canonical_name, patterns)


def extract_skills(text: str) -> set:
    """
    Same interface as skill_extractor.extract_skills() in Phase 1 - takes raw
    text, returns a set of canonical skill names. This means fetch_jobs.py
    can swap which extractor it imports without changing any other code.
    """
    if not text:
        return set()

    doc = _nlp(text)
    matches = _matcher(doc)

    found = set()
    for match_id, start, end in matches:
        canonical_name = _nlp.vocab.strings[match_id]
        found.add(canonical_name)
    return found


if __name__ == "__main__":
    # Same sample sentence used to test the Phase 1 regex extractor -
    # run both files and diff the output to sanity-check they agree.
    sample = """
    We are hiring a fresher Data Analyst. Required skills: SQL, Excel,
    Power BI, and basic Python (pandas/numpy). Exposure to Tableau or
    machine learning is a plus. Familiarity with Git and AWS preferred.
    """
    result = extract_skills(sample)
    print(f"Found {len(result)} skills: {sorted(result)}")
