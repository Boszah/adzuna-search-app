"""
Adzuna Job Search — interactive lookup app
------------------------------------------
A small Streamlit app that lets you search Adzuna for jobs by keyword
and location, browse results in your browser, and download a CSV.

Setup (one-off):
    pip3 install streamlit requests pandas

Run:
    streamlit run adzuna_search_app.py

The first time you launch it, paste your Adzuna API credentials into
the sidebar and click "Save credentials". They'll be saved to
~/.adzuna_creds.json so you don't have to re-enter them next time.
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

CREDS_FILE = Path.home() / ".adzuna_creds.json"

COUNTRIES = {
    "United Kingdom": "gb",
    "United States":  "us",
    "Australia":      "au",
    "Canada":         "ca",
    "Germany":        "de",
    "France":         "fr",
    "Netherlands":    "nl",
    "Italy":          "it",
    "Spain":          "es",
    "Singapore":      "sg",
    "South Africa":   "za",
    "India":          "in",
    "Brazil":         "br",
    "Poland":         "pl",
    "New Zealand":    "nz",
    "Russia":         "ru",
    "Mexico":         "mx",
    "Austria":        "at",
}


def load_creds() -> dict:
    """Load creds, with this priority:
       1. Streamlit Cloud secrets ([adzuna] section)
       2. Local file ~/.adzuna_creds.json
       3. Empty
    """
    # 1. st.secrets (works on Streamlit Cloud + a local secrets.toml file)
    try:
        sec = st.secrets.get("adzuna", {})
        if sec.get("app_id") and sec.get("app_key"):
            return {"app_id": sec["app_id"], "app_key": sec["app_key"]}
    except Exception:
        pass
    # 2. local file
    if CREDS_FILE.exists():
        try:
            return json.loads(CREDS_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_creds(app_id: str, app_key: str) -> bool:
    """Try to persist to disk. Returns False on cloud where disk is ephemeral."""
    try:
        CREDS_FILE.write_text(json.dumps({"app_id": app_id, "app_key": app_key}))
        return True
    except Exception:
        return False


def fmt_salary(job: dict) -> str:
    lo = job.get("salary_min")
    hi = job.get("salary_max")
    if lo and hi and lo != hi:
        return f"£{int(lo):,} – £{int(hi):,}"
    if lo:
        return f"£{int(lo):,}"
    return ""


def fmt_date(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).strftime("%d %b %Y")
    except Exception:
        return iso_str[:10]


def fetch_jobs(country: str, app_id: str, app_key: str, *,
               keyword: str, location: str, max_results: int,
               max_days_old: int, sort_by: str, distance_km: int) -> list:
    """Page through Adzuna's API and return up to max_results jobs."""
    all_results: list = []
    per_page = 50
    pages_needed = (max_results + per_page - 1) // per_page

    progress = st.progress(0.0, text="Searching Adzuna…")
    for page in range(1, pages_needed + 1):
        if len(all_results) >= max_results:
            break

        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
        params = {
            "app_id":           app_id,
            "app_key":          app_key,
            "results_per_page": per_page,
            "what":             keyword,
            "max_days_old":     max_days_old,
            "sort_by":          sort_by,
            "content-type":     "application/json",
        }
        if location:
            params["where"] = location
            params["distance"] = distance_km

        try:
            r = requests.get(url, params=params, timeout=30)
        except requests.exceptions.RequestException as e:
            st.error(f"Network error: {e}")
            return all_results

        if r.status_code == 401:
            st.error("401 Unauthorized — check your App ID and App Key.")
            return all_results
        if r.status_code == 429:
            st.warning("Rate-limited by Adzuna. Try again in a minute.")
            return all_results
        if not r.ok:
            st.error(f"API error: {r.status_code} {r.reason}")
            return all_results

        data = r.json()
        page_results = data.get("results", [])
        if not page_results:
            break
        all_results.extend(page_results)
        progress.progress(min(1.0, len(all_results) / max_results),
                          text=f"Fetched {len(all_results):,} jobs so far…")

    progress.empty()
    return all_results[:max_results]


# =====================================================================
# UI
# =====================================================================

st.set_page_config(
    page_title="Adzuna Job Search",
    page_icon="A",
    layout="wide",
)

if "creds" not in st.session_state:
    st.session_state.creds = load_creds()

# ---- Sidebar: credentials ----
with st.sidebar:
    st.header("Adzuna API")
    st.caption("Get keys at https://developer.adzuna.com/signup")
    app_id_in  = st.text_input("App ID",  value=st.session_state.creds.get("app_id",  ""),
                               type="password")
    app_key_in = st.text_input("App Key", value=st.session_state.creds.get("app_key", ""),
                               type="password")
    if st.button("Save credentials"):
        st.session_state.creds = {"app_id": app_id_in, "app_key": app_key_in}
        persisted = save_creds(app_id_in, app_key_in)
        if persisted:
            st.success("Saved (persists across sessions).")
        else:
            st.success("Saved for this session.")
            st.caption("Persistent disk isn't writable here — you'll need to "
                       "re-enter on next visit, or set keys via Streamlit "
                       "Cloud secrets.")
    st.markdown("---")
    st.caption(
        "Credentials are stored locally in ~/.adzuna_creds.json — never sent "
        "anywhere except Adzuna."
    )

# ---- Main: search form ----
st.title("Adzuna Job Search")
st.caption(
    "Quick interactive search over Adzuna's job index. "
    "Type a keyword and (optionally) a location, hit Search, "
    "browse results and download as CSV."
)

with st.form("search_form"):
    col_a, col_b = st.columns([3, 2])
    with col_a:
        keyword = st.text_input(
            "Job title / keyword",
            placeholder="e.g. Software Engineer, .NET Developer, Patent Attorney",
        )
    with col_b:
        country_label = st.selectbox("Country", list(COUNTRIES.keys()), index=0)

    col_c, col_d, col_e = st.columns([2, 1, 1])
    with col_c:
        location = st.text_input(
            "Location (optional)",
            placeholder="e.g. London, M1, Edinburgh — leave blank for whole country",
        )
    with col_d:
        distance_km = st.number_input("Within (km)", min_value=0, max_value=200,
                                      value=20, step=5,
                                      help="Search radius around the location.")
    with col_e:
        max_days_old = st.number_input("Posted within (days)", min_value=1,
                                       max_value=90, value=30, step=1)

    col_f, col_g = st.columns([1, 1])
    with col_f:
        max_results = st.slider("Max results", min_value=10, max_value=500,
                                value=100, step=10)
    with col_g:
        sort_by = st.selectbox("Sort by", ["relevance", "date", "salary"], index=0)

    submitted = st.form_submit_button("Search", type="primary")

# ---- Run search ----
if submitted:
    creds = st.session_state.creds
    if not creds.get("app_id") or not creds.get("app_key"):
        st.error("Enter your Adzuna API credentials in the sidebar first, "
                 "then click Save credentials.")
        st.stop()
    if not keyword.strip():
        st.error("Enter a job title or keyword to search for.")
        st.stop()

    country = COUNTRIES[country_label]
    results = fetch_jobs(
        country=country,
        app_id=creds["app_id"],
        app_key=creds["app_key"],
        keyword=keyword.strip(),
        location=location.strip(),
        max_results=int(max_results),
        max_days_old=int(max_days_old),
        sort_by=sort_by,
        distance_km=int(distance_km),
    )

    if not results:
        st.warning("No results found. Try broadening the location or keyword.")
        st.stop()

    df = pd.DataFrame([
        {
            "Company":     (j.get("company")  or {}).get("display_name", ""),
            "Title":       (j.get("title")    or "").strip(),
            "Location":    (j.get("location") or {}).get("display_name", ""),
            "Salary":      fmt_salary(j),
            "Contract":    j.get("contract_time", "") or j.get("contract_type", ""),
            "Posted":      fmt_date(j.get("created", "")),
            "Description": ((j.get("description") or "")[:240]).replace("\n", " "),
            "Link":        j.get("redirect_url", ""),
        }
        for j in results
    ])

    st.success(f"Found {len(df):,} results.")

    # ---- Stats panel ----
    c1, c2, c3 = st.columns(3)
    c1.metric("Total roles", f"{len(df):,}")
    c2.metric("Unique companies", f"{df['Company'].nunique():,}")
    c3.metric("Unique locations", f"{df['Location'].nunique():,}")

    # ---- Top hiring companies ----
    if len(df) >= 5:
        with st.expander("Top hiring companies in this search", expanded=True):
            top = (df.assign(c=1)
                     .groupby("Company", as_index=False)["c"].sum()
                     .sort_values("c", ascending=False)
                     .head(15)
                     .rename(columns={"c": "Open roles"}))
            st.dataframe(top, use_container_width=True, hide_index=True)

    # ---- Results table ----
    st.subheader("All results")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Link": st.column_config.LinkColumn("Link", display_text="Open"),
            "Description": st.column_config.TextColumn("Description", width="large"),
        },
    )

    # ---- Download CSV ----
    safe_keyword = "".join(c if c.isalnum() else "_" for c in keyword)
    safe_loc     = "".join(c if c.isalnum() else "_" for c in location) or "anywhere"
    fname = f"adzuna_{safe_keyword}_{safe_loc}_{datetime.now():%Y%m%d}.csv"

    st.download_button(
        "Download results as CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=fname,
        mime="text/csv",
        type="primary",
    )

else:
    st.info(
        "Enter a keyword (and optionally a location) above, then hit "
        "**Search**. Set your Adzuna API keys in the sidebar first if "
        "you haven't already."
    )
