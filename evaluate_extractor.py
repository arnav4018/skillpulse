"""
evaluate_extractor.py

A small measurement harness, used in two steps:

    python evaluate_extractor.py label --n 20
        Shows you N real postings from your database, one at a time. You type
        the skills you can see with your own eyes (comma-separated). Saved to
        labels.json. Skip a posting with Enter if the text is unreadable/junk.

    python evaluate_extractor.py score
        Runs the CURRENT extractor (whatever nlp_skill_extractor.extract_skills
        currently does) against the same postings you labeled, and reports
        precision/recall/F1 against your own labels.

WORKFLOW (do this in order):
    1. Run `label` once now, before changing the vocabulary. This captures
       your BASELINE.
    2. Run `score` now, and save/note the numbers it prints.
    3. Expand SKILL_TAXONOMY (add more skills/aliases).
    4. Run `score` again (no need to re-label). Compare the two number sets.

WHY GROUND TRUTH IS SPLIT INTO "IN VOCAB" AND "OUT OF VOCAB" BELOW:
    If you list a skill the extractor can never have caught because it isn't
    in SKILL_TAXONOMY at all, that's not a matching failure - it's a
    vocabulary gap. Conflating the two would make your recall score look
    artificially bad in a way that expanding aliases (without adding new
    skills) can't fix. Separating them tells you WHICH kind of fix is needed.
"""

import argparse
import json
import os
import random
import sqlite3

from nlp_skill_extractor import extract_skills
from skills_taxonomy import SKILL_TAXONOMY

DB_PATH = os.path.join(os.path.dirname(__file__), "job_tracker.db")
LABELS_PATH = os.path.join(os.path.dirname(__file__), "labels.json")

import re


def normalize_to_canonical(typed_skill: str):
    """
    Try to map a hand-typed label to a canonical taxonomy skill, checking:
    1. exact match against the canonical name
    2. exact match against any of that skill's aliases
    3. an alias appearing INSIDE the typed phrase, as a whole word/phrase
       (word-boundary checked - same \\b logic as skill_extractor.py, so a
       short alias like "r" can't accidentally match inside "Platform")
    Returns the canonical name, or None if this is genuinely out of vocabulary.
    """
    typed_lower = typed_skill.strip().lower()
    for canonical_name, aliases in SKILL_TAXONOMY.items():
        if typed_lower == canonical_name.lower():
            return canonical_name
        for alias in aliases:
            alias_lower = alias.strip().lower()
            if typed_lower == alias_lower:
                return canonical_name
            if re.search(r"\b" + re.escape(alias_lower) + r"\b", typed_lower):
                return canonical_name
    return None


def load_labels() -> dict:
    if os.path.exists(LABELS_PATH):
        with open(LABELS_PATH, "r") as f:
            return json.load(f)
    return {}


def save_labels(labels: dict):
    with open(LABELS_PATH, "w") as f:
        json.dump(labels, f, indent=2)


def cmd_label(n: int):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT job_id, title, description_snippet FROM postings"
    ).fetchall()
    conn.close()

    if not rows:
        print("No postings found. Run fetch_jobs.py first.")
        return

    labels = load_labels()
    already_labeled = set(labels.keys())
    candidates = [r for r in rows if r[0] not in already_labeled]
    random.shuffle(candidates)
    sample = candidates[:n]

    if not sample:
        print("Nothing left to label (or increase --n). Run `score` instead.")
        return

    print(f"Labeling {len(sample)} postings. For each, type the skills you see,")
    print("comma-separated (e.g. 'SQL, Excel, Power BI'). Press Enter alone to skip.\n")

    for job_id, title, description in sample:
        print("-" * 70)
        print(f"TITLE: {title}")
        print(f"DESCRIPTION: {description}")
        raw = input("\nSkills you see (comma-separated, Enter to skip): ").strip()
        if raw:
            skill_list = [s.strip() for s in raw.split(",") if s.strip()]
            labels[job_id] = skill_list
            save_labels(labels)  # save after every single one - don't lose progress
        print()

    print(f"Done. {len(labels)} total postings labeled so far, saved to labels.json")


def cmd_score():
    labels = load_labels()
    if not labels:
        print("No labels found. Run `label` first.")
        return

    conn = sqlite3.connect(DB_PATH)

    total_tp = 0
    total_fp = 0
    total_fn_in_vocab = 0
    total_fn_out_of_vocab = 0

    from collections import Counter
    out_of_vocab_counter = Counter()   # which missing skills, and how often
    false_positive_examples = []       # (title, skill) pairs to eyeball

    for job_id, your_skills in labels.items():
        row = conn.execute(
            "SELECT title, description_snippet FROM postings WHERE job_id = ?", (job_id,)
        ).fetchone()
        if not row:
            continue
        title, description = row
        predicted = extract_skills(f"{title} {description}")

        ground_truth_in_vocab = set()
        ground_truth_out_of_vocab = set()
        for s in your_skills:
            canonical = normalize_to_canonical(s)
            if canonical:
                ground_truth_in_vocab.add(canonical)
            else:
                ground_truth_out_of_vocab.add(s.strip())

        tp = predicted & ground_truth_in_vocab
        fp = predicted - ground_truth_in_vocab
        fn_in_vocab = ground_truth_in_vocab - predicted

        total_tp += len(tp)
        total_fp += len(fp)
        total_fn_in_vocab += len(fn_in_vocab)
        total_fn_out_of_vocab += len(ground_truth_out_of_vocab)

        for skill in ground_truth_out_of_vocab:
            out_of_vocab_counter[skill.lower()] += 1
        for skill in fp:
            false_positive_examples.append((title, skill))

    conn.close()

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0
    recall_in_vocab = total_tp / (total_tp + total_fn_in_vocab) if (total_tp + total_fn_in_vocab) else 0
    f1 = (2 * precision * recall_in_vocab / (precision + recall_in_vocab)) if (precision + recall_in_vocab) else 0

    print(f"Labeled postings scored: {len(labels)}")
    print(f"True positives:  {total_tp}")
    print(f"False positives: {total_fp}  (extractor over-matched)")
    print(f"False negatives (in-vocab, real miss):     {total_fn_in_vocab}")
    print(f"False negatives (out-of-vocab, not fixable without adding the skill): {total_fn_out_of_vocab}")
    print()
    print(f"Precision:            {precision:.2f}")
    print(f"Recall (in-vocab):    {recall_in_vocab:.2f}")
    print(f"F1 (in-vocab):        {f1:.2f}")

    print("\n--- Vocabulary expansion candidates (skill: how many postings mentioned it) ---")
    for skill, count in out_of_vocab_counter.most_common():
        print(f"  {skill}: {count}")

    print("\n--- False positive examples (extractor found this, you didn't list it) ---")
    for title, skill in false_positive_examples:
        print(f"  [{title}] -> {skill}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Label postings and score the skill extractor.")
    sub = parser.add_subparsers(dest="command", required=True)

    label_parser = sub.add_parser("label", help="Hand-label a sample of postings")
    label_parser.add_argument("--n", type=int, default=20, help="Number of postings to label")

    sub.add_parser("score", help="Score the current extractor against saved labels")

    args = parser.parse_args()
    if args.command == "label":
        cmd_label(args.n)
    elif args.command == "score":
        cmd_score()
