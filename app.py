import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import io
import re
from urllib.parse import quote

# -------------------- CONFIG -------------------- #
PMC_OAI_URL = "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"

MAX_RECORDS = 200   # safety limit (can increase slowly)

# -------------------- PAGE CONFIG -------------------- #
st.set_page_config(
    page_title="PMC OAI-PMH Search App",
    page_icon="📄",
    layout="wide"
)

st.title("📄 PMC Full-Text Search (OAI-PMH)")
st.caption("Uses PMC OAI-PMH metadata harvesting + local keyword filtering")

# -------------------- INPUT -------------------- #
search_query = st.text_input(
    "Enter search keywords (title / abstract)",
    "antibacterial suture"
)

from_year, to_year = st.slider(
    "Publication year range",
    1990, 2025, (2000, 2025)
)

max_results = st.number_input(
    "Maximum results to fetch",
    min_value=10,
    max_value=1000,
    value=100,
    step=10
)

# -------------------- HELPERS -------------------- #
def text_match(text, query):
    if not text:
        return False
    words = query.lower().split()
    text = text.lower()
    return all(w in text for w in words)

def fetch_pmc_oai_records(max_records=100):
    """
    Fetch PMC records using OAI-PMH ListRecords
    """
    records = []
    params = {
        "verb": "ListRecords",
        "metadataPrefix": "oai_dc"
    }

    while True:
        r = requests.get(PMC_OAI_URL, params=params, timeout=30)
        r.raise_for_status()

        root = ET.fromstring(r.text)
        ns = {
            "oai": "http://www.openarchives.org/OAI/2.0/",
            "dc": "http://purl.org/dc/elements/1.1/"
        }

        for rec in root.findall(".//oai:record", ns):
            meta = rec.find("oai:metadata", ns)
            if meta is None:
                continue

            dc = meta.find("dc:dc", ns)
            if dc is None:
                continue

            title = "; ".join([e.text for e in dc.findall("dc:title", ns) if e.text])
            creators = "; ".join([e.text for e in dc.findall("dc:creator", ns) if e.text])
            identifiers = [e.text for e in dc.findall("dc:identifier", ns) if e.text]
            dates = [e.text for e in dc.findall("dc:date", ns) if e.text]

            pmcid = ""
            doi = ""

            for i in identifiers:
                if i.startswith("PMC"):
                    pmcid = i
                if i.startswith("10."):
                    doi = i

            year = ""
            if dates:
                m = re.search(r"\d{4}", dates[0])
                if m:
                    year = m.group()

            records.append({
                "Title": title,
                "Authors": creators,
                "Year": year,
                "PMCID": pmcid,
                "DOI": doi
            })

            if len(records) >= max_records:
                return records

        token = root.find(".//oai:resumptionToken", ns)
        if token is None or not token.text:
            break

        params = {
            "verb": "ListRecords",
            "resumptionToken": token.text
        }

    return records

# -------------------- MAIN -------------------- #
if st.button("🔍 Fetch PMC Results"):

    with st.spinner("Fetching PMC records via OAI-PMH..."):
        raw_records = fetch_pmc_oai_records(max_results)

    # Local keyword filtering
    filtered = []
    for r in raw_records:
        if (
            text_match(r["Title"], search_query)
            and (not r["Year"] or from_year <= int(r["Year"]) <= to_year)
        ):
            filtered.append(r)

    df = pd.DataFrame(filtered)

    st.success(f"Found {len(df)} matching PMC articles")

    if not df.empty:
        st.dataframe(df, use_container_width=True)

        # -------------------- DOWNLOADS -------------------- #
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)

        st.download_button(
            "⬇️ Download CSV",
            csv_buf.getvalue(),
            file_name="pmc_results.csv",
            mime="text/csv"
        )

        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="PMC Results")
        excel_buf.seek(0)

        st.download_button(
            "⬇️ Download Excel",
            excel_buf,
            file_name="pmc_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # -------------------- DIRECT PMC SEARCH LINK -------------------- #
    st.divider()
    st.subheader("🔗 Direct PMC Search (Complete Results)")
    pmc_search_url = (
        "https://www.ncbi.nlm.nih.gov/pmc/?term="
        + quote(search_query)
    )
    st.markdown(f"[Open full PMC search results]({pmc_search_url})")

    st.info(
        "PMC OAI-PMH does not support keyword search directly. "
        "This app fetches metadata and filters locally. "
        "For complete results, always use the direct PMC search link."
    )
