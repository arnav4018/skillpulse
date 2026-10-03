"""
app.py

SkillPulse Streamlit dashboard - Phase 3.

See earlier revision's docstring for the overall design reasoning (Streamlit
over a custom web app, logic kept in separate tested modules). This version
adds: Plotly charts (interactive, replacing the plain bar chart), a Top
Hiring Companies view, a first real Skill Trends tab, clickable "Apply"
links, and CSV export of resume-match results.

WHY THE TRENDS TAB USES first_seen_date, NOT A DIRECT "SKILLS PER WEEK" TABLE:
    The schema attaches skills to POSTINGS, not to individual collection
    runs - a posting's skill set doesn't change after it's first extracted.
    What CAN change over time is WHICH postings exist. Grouping by
    first_seen_date (the week a posting first entered the dataset) is the
    honest proxy available: "how many postings mentioning skill X first
    appeared each week" - not a perfect trend line, and said so in the UI,
    but a real signal built from real schema fields rather than something
    invented to look impressive.

RUN THIS WITH:
    streamlit run app.py
"""

import os
import sqlite3
import tempfile

import pandas as pd
import plotly.express as px
import streamlit as st

from resume_matcher import (
    get_market_skill_frequencies,
    get_posting_skill_map,
    compute_skill_gap,
    find_best_matches,
    load_resume_text,
)
from nlp_skill_extractor import extract_skills

DB_PATH = os.path.join(os.path.dirname(__file__), "job_tracker.db")

st.set_page_config(page_title="SkillPulse", page_icon="📊", layout="wide")

# Custom CSS - Streamlit's default look is plain by design; this is the
# standard, supported way to restyle it without a separate frontend build.
# Every rule here targets Streamlit's own emitted class names, so it stays
# a pure styling layer on top of the same components used elsewhere in this
# file - nothing here changes what data is shown, only how it looks.
st.markdown(
    """
    <style>
    /* Card-style metric boxes */
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #ffffff, #f2f4f8);
        border: 1px solid #e3e7f0;
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: 0 2px 6px rgba(26, 43, 76, 0.06);
    }
    div[data-testid="stMetricValue"] { color: #2f6fed; font-weight: 700; }

    /* Bolder, clearer tabs */
    button[data-baseweb="tab"] {
        font-size: 1.02rem;
        font-weight: 600;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #2f6fed;
        border-bottom: 3px solid #2f6fed;
    }

    /* Rounded, shadowed tables */
    div[data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 1px 4px rgba(26, 43, 76, 0.08);
    }

    /* Buttons & link-buttons */
    .stButton button, .stLinkButton a, .stDownloadButton button {
        border-radius: 8px;
        font-weight: 600;
        transition: transform 0.08s ease, box-shadow 0.08s ease;
    }
    .stButton button:hover, .stLinkButton a:hover, .stDownloadButton button:hover {
        transform: translateY(-1px);
        box-shadow: 0 3px 8px rgba(47, 111, 237, 0.25);
    }

    /* Expander cards (resume match results) */
    div[data-testid="stExpander"] {
        border-radius: 10px;
        border: 1px solid #e3e7f0;
        box-shadow: 0 1px 3px rgba(26, 43, 76, 0.05);
    }

    /* Tighter, cleaner page title area */
    h1 { font-weight: 800; letter-spacing: -0.5px; }

    /* Hide the default "Made with Streamlit" footer for a cleaner look */
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_connection():
    """Shared, cached DB connection - see earlier revision's docstring for why caching matters here."""
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def render_market_overview(conn):
    st.header("📈 Market Overview")

    total_postings = conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
    fresher_postings = conn.execute(
        "SELECT COUNT(*) FROM postings WHERE is_fresher_heuristic = 1"
    ).fetchone()[0]
    total_runs = conn.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0]
    total_companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📄 Total postings", total_postings)
    col2.metric("🌱 Fresher-flagged", fresher_postings)
    col3.metric("🏢 Companies seen", total_companies)
    col4.metric("🔄 Collection runs", total_runs)

    latest_run = conn.execute(
        "SELECT run_timestamp FROM search_runs ORDER BY run_timestamp DESC LIMIT 1"
    ).fetchone()
    if latest_run:
        st.caption(f"🕒 Last collected: {latest_run[0]}")

    st.caption(
        "Fresher flag is a keyword heuristic on title/description (Adzuna has no "
        "native experience-level filter) - treat this as a lower bound, not exact."
    )

    st.divider()

    left, right = st.columns([3, 2])

    with left:
        st.subheader("Top skills across all collected postings")
        market_freq = get_market_skill_frequencies(conn)
        if market_freq:
            top_n = st.slider("Show top N skills", min_value=5, max_value=30, value=15)
            df = pd.DataFrame(market_freq[:top_n], columns=["Skill", "Mentions"])
            fig = px.bar(
                df.sort_values("Mentions"), x="Mentions", y="Skill", orientation="h",
                color="Mentions", color_continuous_scale="Blues",
            )
            fig.update_layout(height=max(350, top_n * 24), showlegend=False, coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No skill data yet - run fetch_jobs.py to collect postings first.")

    with right:
        st.subheader("Top hiring companies")
        company_rows = conn.execute(
            """SELECT c.company_name, COUNT(*) as n
               FROM postings p JOIN companies c ON c.company_id = p.company_id
               GROUP BY c.company_name ORDER BY n DESC LIMIT 10"""
        ).fetchall()
        if company_rows:
            df_c = pd.DataFrame(company_rows, columns=["Company", "Postings"])
            fig_c = px.bar(df_c.sort_values("Postings"), x="Postings", y="Company", orientation="h")
            fig_c.update_traces(marker_color="#2f6fed")
            fig_c.update_layout(height=380, showlegend=False)
            st.plotly_chart(fig_c, width="stretch")
        else:
            st.info("No company data yet.")


def render_skill_trends(conn):
    st.header("📊 Skill Trends")
    st.caption(
        "Built from each posting's first_seen_date - when it first entered the "
        "database via a scheduled collection run. With only a few collection runs "
        "so far, treat this as an early look, not a settled trend."
    )

    rows = conn.execute(
        """SELECT p.first_seen_date, s.skill_name
           FROM postings p
           JOIN posting_skills ps ON p.job_id = ps.job_id
           JOIN skills s ON s.skill_id = ps.skill_id
           WHERE p.first_seen_date IS NOT NULL"""
    ).fetchall()

    if not rows:
        st.info("No data yet - run fetch_jobs.py first.")
        return

    df = pd.DataFrame(rows, columns=["first_seen_date", "skill"])
    df["first_seen_date"] = pd.to_datetime(df["first_seen_date"], errors="coerce")
    df = df.dropna(subset=["first_seen_date"])

    # Pick bucket size based on how much calendar time the data actually
    # spans - weekly buckets are meaningless (or actively misleading, as
    # found during testing) when all the data falls inside one week, so
    # default to daily until there's enough history for weekly to make sense.
    span_days = (df["first_seen_date"].max() - df["first_seen_date"].min()).days
    default_grouping = "Day" if span_days < 14 else "Week"
    grouping = st.radio("Group by", options=["Day", "Week"], index=0 if default_grouping == "Day" else 1, horizontal=True)

    if grouping == "Day":
        df["bucket"] = df["first_seen_date"].dt.normalize()
    else:
        df["bucket"] = df["first_seen_date"].dt.to_period("W").dt.start_time

    top_skills = df["skill"].value_counts().head(8).index.tolist()
    default_selection = top_skills[:5]
    chosen = st.multiselect("Skills to compare", options=sorted(df["skill"].unique()), default=default_selection)

    if not chosen:
        st.info("Pick at least one skill above to see its trend.")
        return

    filtered = df[df["skill"].isin(chosen)]
    bucketed = filtered.groupby(["bucket", "skill"]).size().reset_index(name="new_postings")

    n_buckets = bucketed["bucket"].nunique()
    if n_buckets < 2:
        st.warning(
            f"All collected data falls into a single {grouping.lower()}-bucket right now - "
            "a trend line needs at least two points in time to show movement. This isn't "
            "an error, just a sign the scheduled collector needs more runs to accumulate "
            "enough history. Showing a snapshot instead:"
        )
        snapshot = filtered.groupby("skill").size().reset_index(name="mentions").sort_values("mentions", ascending=False)
        fig = px.bar(snapshot, x="mentions", y="skill", orientation="h")
        fig.update_layout(height=max(300, len(chosen) * 40), showlegend=False)
        st.plotly_chart(fig, width="stretch")
        return

    fig = px.line(bucketed, x="bucket", y="new_postings", color="skill", markers=True)
    fig.update_layout(height=420, xaxis_title=f"{grouping} first seen", yaxis_title="New postings mentioning skill")
    st.plotly_chart(fig, width="stretch")

    if n_buckets < 3:
        st.warning(
            f"Only {n_buckets} distinct {grouping.lower()}(s) of data so far - let the "
            "scheduled collector run for longer before drawing firm conclusions from this chart."
        )


def render_postings_browser(conn):
    st.header("🗂️ Browse Postings")

    show_fresher_only = st.checkbox("Show only fresher-flagged postings")

    query = "SELECT title, location_display, created_at_source, is_fresher_heuristic, redirect_url FROM postings"
    if show_fresher_only:
        query += " WHERE is_fresher_heuristic = 1"
    query += " ORDER BY created_at_source DESC LIMIT 100"

    rows = conn.execute(query).fetchall()
    if not rows:
        st.info("No postings match this filter.")
        return

    df = pd.DataFrame(
        [
            {
                "Title": title,
                "Location": location or "-",
                "Posted": created or "-",
                "Fresher-flagged": "🌱 Fresher" if is_fresher else "—",
                "Apply": url or "",
            }
            for title, location, created, is_fresher, url in rows
        ]
    )
    st.dataframe(
        df,
        width="stretch",
        column_config={"Apply": st.column_config.LinkColumn("Apply", display_text="Open ↗")},
    )
    st.caption(f"Showing {len(rows)} most recent postings.")


def render_resume_matcher(conn):
    st.header("📝 Resume Matcher")
    st.write(
        "Upload a resume (PDF or .txt) to see which in-demand skills you're "
        "missing, and which collected postings best match what you already know."
    )

    uploaded_file = st.file_uploader("Upload resume", type=["pdf", "txt"])
    pasted_text = st.text_area("...or paste resume text directly", height=150)

    resume_text = None
    if uploaded_file is not None:
        suffix = ".pdf" if uploaded_file.name.lower().endswith(".pdf") else ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name
        try:
            resume_text = load_resume_text(tmp_path)
        finally:
            os.remove(tmp_path)
    elif pasted_text.strip():
        resume_text = pasted_text

    if not resume_text:
        st.info("Upload a file or paste text above to see results.")
        return

    resume_skills = extract_skills(resume_text)

    if not resume_skills:
        st.warning(
            "No known skills detected in this resume. Either the resume genuinely "
            "doesn't mention any taxonomy skills, or (if this was a PDF) text "
            "extraction may have failed - check for a warning above."
        )
        return

    st.success(f"Detected {len(resume_skills)} skills: {', '.join(sorted(resume_skills))}")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Skill gap")
        st.caption("Top in-demand skills this resume doesn't show")
        market_freq = get_market_skill_frequencies(conn)
        gap = compute_skill_gap(resume_skills, market_freq, top_n=15)
        if gap:
            for skill in gap:
                st.write(f"- {skill}")
        else:
            st.write("None - resume covers all top 15 in-demand skills.")

    with col2:
        st.subheader("Best-matching postings")
        posting_map = get_posting_skill_map(conn)
        matches = find_best_matches(resume_skills, posting_map, top_n=10)
        if not matches:
            st.write("No postings with overlapping skills found.")
        else:
            match_rows = []
            for job_id, title, company, redirect_url, overlap_count, matched, missing in matches:
                with st.expander(f"{title} @ {company or 'Unknown'} — {overlap_count} skills matched"):
                    st.write(f"**Matched:** {', '.join(sorted(matched))}")
                    if missing:
                        st.write(f"**Still missing:** {', '.join(sorted(missing))}")
                    if redirect_url:
                        st.link_button("Apply ↗", redirect_url)
                match_rows.append({
                    "Title": title, "Company": company or "Unknown",
                    "Skills matched": overlap_count,
                    "Matched": ", ".join(sorted(matched)),
                    "Missing": ", ".join(sorted(missing)),
                    "Apply": redirect_url or "",
                })

            csv_data = pd.DataFrame(match_rows).to_csv(index=False)
            st.download_button("Download matches as CSV", csv_data, file_name="skillpulse_matches.csv", mime="text/csv")


def main():
    st.title("📊 SkillPulse")
    st.caption("Fresher Job Market Intelligence & Skill-Trend Tracker")

    conn = get_connection()

    tab1, tab2, tab3, tab4 = st.tabs(["Market Overview", "Skill Trends", "Browse Postings", "Resume Matcher"])
    with tab1:
        render_market_overview(conn)
    with tab2:
        render_skill_trends(conn)
    with tab3:
        render_postings_browser(conn)
    with tab4:
        render_resume_matcher(conn)


if __name__ == "__main__":
    main()
