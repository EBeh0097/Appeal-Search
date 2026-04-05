import streamlit as st
import pandas as pd
import requests

st.set_page_config(
    page_title="CMS Appeals Search",
    page_icon="⚖️",
    layout="wide",
)

st.title("⚖️ CMS Appeals Search")
st.markdown(
    "Search Medicare and Medicaid appeal decisions from the "
    "Centers for Medicare & Medicaid Services (CMS)."
)

# ── Sidebar filters ─────────────────────────────────────────────────────────
st.sidebar.header("Search Filters")

keyword = st.sidebar.text_input("Keyword", placeholder="e.g. home health, denial")

appeal_type = st.sidebar.selectbox(
    "Appeal Type",
    options=["All", "Medicare", "Medicaid", "Part A", "Part B", "Part C", "Part D"],
)

date_range = st.sidebar.date_input(
    "Decision Date Range",
    value=[],
    help="Select a start and end date to filter results.",
)

search_btn = st.sidebar.button("🔍 Search", use_container_width=True)

# ── Sample / demo data ───────────────────────────────────────────────────────
SAMPLE_DATA = [
    {
        "Case ID": "CMS-2024-00123",
        "Appeal Type": "Medicare Part A",
        "Decision Date": "2024-03-15",
        "Outcome": "Overturned",
        "Summary": "Inpatient hospital admission denied; reversed on appeal due to medical necessity documentation.",
    },
    {
        "Case ID": "CMS-2024-00456",
        "Appeal Type": "Medicare Part B",
        "Decision Date": "2024-02-28",
        "Outcome": "Upheld",
        "Summary": "Durable medical equipment claim denied; original determination upheld.",
    },
    {
        "Case ID": "CMS-2024-00789",
        "Appeal Type": "Medicaid",
        "Decision Date": "2024-01-10",
        "Outcome": "Overturned",
        "Summary": "Home health services denied; reversed after review of physician orders.",
    },
    {
        "Case ID": "CMS-2023-01001",
        "Appeal Type": "Medicare Part D",
        "Decision Date": "2023-12-05",
        "Outcome": "Upheld",
        "Summary": "Prescription drug coverage exception denied; original decision upheld.",
    },
    {
        "Case ID": "CMS-2023-01234",
        "Appeal Type": "Medicare Part C",
        "Decision Date": "2023-11-20",
        "Outcome": "Overturned",
        "Summary": "Prior authorization for specialist visit denied; reversed on appeal.",
    },
    {
        "Case ID": "CMS-2023-01567",
        "Appeal Type": "Medicare Part A",
        "Decision Date": "2023-10-08",
        "Outcome": "Remanded",
        "Summary": "Skilled nursing facility coverage; remanded for additional documentation.",
    },
]

# ── Search logic ─────────────────────────────────────────────────────────────
def filter_records(records, keyword, appeal_type, date_range):
    results = records

    if keyword:
        kw = keyword.lower()
        results = [
            r for r in results
            if kw in r["Summary"].lower()
            or kw in r["Case ID"].lower()
            or kw in r["Appeal Type"].lower()
        ]

    if appeal_type and appeal_type != "All":
        results = [r for r in results if appeal_type.lower() in r["Appeal Type"].lower()]

    if len(date_range) == 2:
        start, end = date_range
        results = [
            r for r in results
            if start.isoformat() <= r["Decision Date"] <= end.isoformat()
        ]

    return results


# ── Display results ──────────────────────────────────────────────────────────
if search_btn or "searched" not in st.session_state:
    st.session_state["searched"] = True
    with st.spinner("Searching…"):
        results = filter_records(SAMPLE_DATA, keyword, appeal_type, date_range)

    st.subheader(f"Results ({len(results)} found)")

    if results:
        df = pd.DataFrame(results)

        # Colour-code outcome column
        def highlight_outcome(val):
            color_map = {
                "Overturned": "background-color: #d4edda; color: #155724",
                "Upheld": "background-color: #f8d7da; color: #721c24",
                "Remanded": "background-color: #fff3cd; color: #856404",
            }
            return color_map.get(val, "")

        styled_df = df.style.map(highlight_outcome, subset=["Outcome"])
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

        # Detail expanders
        st.markdown("---")
        st.subheader("Case Details")
        for record in results:
            with st.expander(f"📄 {record['Case ID']} — {record['Outcome']}"):
                col1, col2, col3 = st.columns(3)
                col1.metric("Appeal Type", record["Appeal Type"])
                col2.metric("Decision Date", record["Decision Date"])
                col3.metric("Outcome", record["Outcome"])
                st.write("**Summary:**", record["Summary"])
    else:
        st.info("No records matched your search criteria. Try adjusting the filters.")

# ── Footer ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "Data shown is for demonstration purposes. "
    "For official CMS appeal decisions, visit [cms.gov](https://www.cms.gov)."
)
