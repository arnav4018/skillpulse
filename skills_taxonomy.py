"""
skills_taxonomy.py

Phase 1 skill extraction = taxonomy/dictionary matching, NOT NLP.

WHY start here instead of NLP (defend this to the panel):
  A curated list + regex matching is transparent, debuggable, and has near-
  100% precision on skills you've explicitly listed (if "SQL" is in the
  taxonomy and the text says "SQL", it WILL match — no model uncertainty).
  Its weakness is recall: it can only ever find skills you thought to add.
  That weakness is exactly the gap Phase 2 closes (spaCy PhraseMatcher /
  a proper NER-style pass can surface skills you didn't manually list).
  Starting with taxonomy matching is a legitimate, deliberate engineering
  choice — not a shortcut you're hiding. Say that explicitly in your report.

Structure: canonical skill name -> list of surface forms (aliases) that
should all map to that one canonical name. This matters because postings
say "Power BI", "PowerBI", "power-bi" etc. and you want ONE skill row, not
three, or your trend counts will be silently wrong.
"""

SKILL_TAXONOMY = {
    # Programming / query languages
    "Python": ["python"],
    "SQL": ["sql", "mysql", "postgresql", "ms sql", "t-sql", "pl/sql"],
    "R": ["r programming", " r,", " r "],  # deliberately narrow — "R" alone is too ambiguous to regex-match safely
    "VBA": ["vba", "visual basic for applications"],

    # Core data/analyst libraries
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Excel": ["excel", "ms excel", "microsoft excel", "advanced excel"],

    # BI / visualization tools
    "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau"],
    "Looker": ["looker"],
    "Qlik": ["qlik", "qlikview", "qliksense"],

    # Databases / warehousing
    "SQL Server": ["sql server", "mssql"],
    "MongoDB": ["mongodb", "mongo db"],
    "Snowflake": ["snowflake"],
    "BigQuery": ["bigquery", "big query"],
    "Redshift": ["redshift"],

    # ML / stats
    "Scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "Machine Learning": ["machine learning", "ml models", " ml,", " ml."],
    "Statistics": ["statistics", "statistical analysis"],
    "A/B Testing": ["a/b testing", "ab testing"],

    # Big data / engineering-adjacent (frequently show up even in analyst postings)
    "Spark": ["apache spark", "pyspark", " spark "],
    "Hadoop": ["hadoop"],
    "Airflow": ["airflow", "apache airflow"],
    "ETL": ["etl", "extract transform load", "extract, transform, load"],

    # Cloud
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure", "microsoft azure"],
    "GCP": ["gcp", "google cloud"],

    # Version control / collaboration
    "Git": ["git", "github", "gitlab"],
    "Jira": ["jira"],

    # Visualization libraries (Python)
    "Matplotlib": ["matplotlib"],
    "Seaborn": ["seaborn"],
    "Plotly": ["plotly"],

    # Soft/analyst-specific terms worth tracking even if not "technical skills"
    "Data Visualization": ["data visualization", "data visualisation"],
    "Dashboarding": ["dashboard", "dashboards", "dashboarding"],
}

# Phrases used to heuristically flag a posting as "fresher / entry-level".
# Adzuna has NO native experience-level filter, so this is a text heuristic
# applied to title + description — flag this explicitly as a limitation in
# your report, not something to quietly gloss over.
FRESHER_KEYWORDS = [
    "fresher", "freshers", "entry level", "entry-level",
    "0-1 year", "0-1 years", "0 to 1 year", "trainee", "graduate trainee",
    "recent graduate", "campus hire", "junior", "0-2 years", "0-2 year",
]
