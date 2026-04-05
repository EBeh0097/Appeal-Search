import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

st.set_page_config(page_title="Medicare Appeals Agent", page_icon="📋", layout="wide")


# -----------------------------
# Security and environment
# -----------------------------
def get_openai_api_key() -> Optional[str]:
    if "OPENAI_API_KEY" in st.secrets:
        return st.secrets["OPENAI_API_KEY"]
    return os.getenv("OPENAI_API_KEY")


def ensure_playwright_browser() -> None:
    """Install Chromium at runtime if it is not already available."""
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/tmp/playwright-browsers")
    browser_dir = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    if os.path.exists(browser_dir) and any(os.scandir(browser_dir)):
        return

    with st.spinner("Installing Playwright Chromium browser for this app session..."):
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Chromium install failed.\n\n"
                f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
            )


# -----------------------------
# Validation helpers
# -----------------------------
def validate_plan_contract(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z]\d{4}", value):
        raise ValueError("Plan Contract # must look like H5215.")
    return value



def validate_short_date(value: str) -> str:
    value = value.strip()
    try:
        datetime.strptime(value, "%m/%d/%Y")
    except ValueError as exc:
        raise ValueError("Date must be in mm/dd/yyyy format, for example 01/01/2025.") from exc
    return value



def validate_date_order(start_date: str, end_date: str) -> None:
    start_dt = datetime.strptime(start_date, "%m/%d/%Y")
    end_dt = datetime.strptime(end_date, "%m/%d/%Y")
    if end_dt < start_dt:
        raise ValueError("End Date cannot be earlier than Start Date.")



def streamlit_date_to_short_str(value: date) -> str:
    return value.strftime("%m/%d/%Y")


# -----------------------------
# Dataframe helpers
# -----------------------------
def make_json_safe(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value



def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")

    if not df.empty:
        first_row = [str(x).strip().lower() for x in df.iloc[0].tolist()]
        cols = [str(x).strip().lower() for x in df.columns.tolist()]
        if first_row == cols:
            df = df.iloc[1:].reset_index(drop=True)

    df = df.loc[:, ~pd.Index(df.columns).duplicated()]
    return df.reset_index(drop=True)



def dataframe_from_html(html: str) -> pd.DataFrame:
    try:
        tables = pd.read_html(StringIO(html))
        tables = [t for t in tables if t.shape[0] > 0 and t.shape[1] > 1]
        if tables:
            df = max(tables, key=lambda x: x.shape[0] * x.shape[1])
            return clean_dataframe(df)
    except Exception:
        pass

    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        headers = [th.get_text(" ", strip=True) for th in rows[0].find_all(["th", "td"])]
        body = []
        for row in rows[1:]:
            vals = [td.get_text(" ", strip=True) for td in row.find_all(["th", "td"])]
            if vals:
                body.append(vals)

        if headers and body:
            max_len = max(len(headers), max(len(r) for r in body))
            headers = headers + [f"col_{i}" for i in range(len(headers), max_len)]
            body = [r + [""] * (max_len - len(r)) for r in body]
            return clean_dataframe(pd.DataFrame(body, columns=headers))

    return pd.DataFrame()


async def get_results_table(page) -> pd.DataFrame:
    html = await page.content()
    return dataframe_from_html(html)


async def try_set_max_page_size(page) -> Optional[str]:
    select_locators = [
        page.locator("select"),
        page.locator("select[name*='PageSize'], select[id*='PageSize']"),
    ]

    for select_group in select_locators:
        count = await select_group.count()
        for i in range(count):
            select = select_group.nth(i)
            try:
                options = await select.locator("option").all_text_contents()
                normalized = [o.strip() for o in options if o.strip()]
                if not normalized:
                    continue

                preferred = None
                if any(o.lower() == "all" for o in normalized):
                    preferred = next(o for o in normalized if o.lower() == "all")
                else:
                    numeric_options = []
                    for o in normalized:
                        match = re.search(r"\d+", o)
                        if match:
                            numeric_options.append((int(match.group()), o))
                    if numeric_options:
                        preferred = max(numeric_options, key=lambda x: x[0])[1]

                if preferred:
                    await select.select_option(label=preferred)
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    await page.wait_for_timeout(1500)
                    return preferred
            except Exception:
                continue
    return None


async def try_click_next(page) -> bool:
    candidates = [
        page.get_by_role("link", name=re.compile(r"^next$", re.I)),
        page.get_by_role("button", name=re.compile(r"^next$", re.I)),
        page.get_by_role("link", name=re.compile(r"^>$")),
        page.get_by_role("button", name=re.compile(r"^>$")),
        page.locator("a[aria-label*='Next'], button[aria-label*='Next']"),
        page.locator("a:has-text('Next'), button:has-text('Next')"),
        page.locator(".paginate_button.next, .pagination-next, li.next a"),
    ]

    for candidate in candidates:
        try:
            if await candidate.count() == 0:
                continue
            btn = candidate.first
            disabled = (await btn.get_attribute("disabled")) or ""
            class_name = (await btn.get_attribute("class")) or ""
            aria_disabled = (await btn.get_attribute("aria-disabled")) or ""
            if (
                "disabled" in disabled.lower()
                or "disabled" in class_name.lower()
                or aria_disabled.lower() == "true"
            ):
                continue

            await btn.click(timeout=5000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await page.wait_for_timeout(1500)
            return True
        except Exception:
            continue

    return False


async def collect_all_pages(page, max_pages: int = 200) -> pd.DataFrame:
    page_size_choice = await try_set_max_page_size(page)

    collected_frames: List[pd.DataFrame] = []
    seen_signatures = set()

    for _ in range(max_pages):
        df_page = await get_results_table(page)
        if df_page.empty:
            break

        signature = (
            tuple(df_page.columns.tolist()),
            tuple(map(tuple, df_page.head(5).astype(str).fillna("").values.tolist())),
            tuple(map(tuple, df_page.tail(5).astype(str).fillna("").values.tolist())),
            df_page.shape,
        )

        if signature in seen_signatures:
            break

        seen_signatures.add(signature)
        collected_frames.append(df_page)

        if page_size_choice and str(page_size_choice).strip().lower() == "all":
            break

        moved = await try_click_next(page)
        if not moved:
            break

    if not collected_frames:
        return pd.DataFrame()

    combined = pd.concat(collected_frames, ignore_index=True)
    combined = combined.drop_duplicates().reset_index(drop=True)
    return clean_dataframe(combined)


# -----------------------------
# Scrape + analysis workflow
# -----------------------------
async def scrape_medicare_appeals(plan_contract: str, start_date: str, end_date: str) -> Dict[str, Any]:
    url = "https://medicareappeals.com/AppealSearch"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)

            plan_locators = [
                page.get_by_label("Plan Contract #", exact=False),
                page.locator("input[name*='Plan'][name*='Contract'], input[id*='Plan'][id*='Contract']"),
                page.locator("input").nth(1),
            ]

            start_locators = [
                page.get_by_label("Start Date", exact=False),
                page.locator("input[name*='Start'][name*='Date'], input[id*='Start'][id*='Date']"),
            ]

            end_locators = [
                page.get_by_label("End Date", exact=False),
                page.locator("input[name*='End'][name*='Date'], input[id*='End'][id*='Date']"),
            ]

            async def fill_first_working(locator_list, value: str) -> None:
                last_error = None
                for loc in locator_list:
                    try:
                        await loc.first.wait_for(timeout=5000)
                        await loc.first.fill("")
                        await loc.first.fill(value)
                        return
                    except Exception as exc:
                        last_error = exc
                if last_error:
                    raise last_error
                raise RuntimeError("No working input locator was found.")

            await fill_first_working(plan_locators, plan_contract)
            await fill_first_working(start_locators, start_date)
            await fill_first_working(end_locators, end_date)

            clicked = False
            button_candidates = [
                page.get_by_role("button", name="Search"),
                page.get_by_text("Search", exact=True),
                page.locator("input[type='submit'][value*='Search'], button:has-text('Search')"),
            ]

            for btn in button_candidates:
                try:
                    await btn.first.click(timeout=5000)
                    clicked = True
                    break
                except Exception:
                    pass

            if not clicked:
                try:
                    await end_locators[0].first.press("Enter")
                    clicked = True
                except Exception:
                    pass

            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            df = await collect_all_pages(page)
            current_url = page.url

            preview_rows_cleaned = []
            all_rows_cleaned = []
            if not df.empty:
                for record in df.head(10).to_dict(orient="records"):
                    preview_rows_cleaned.append({k: make_json_safe(v) for k, v in record.items()})
                for record in df.to_dict(orient="records"):
                    all_rows_cleaned.append({k: make_json_safe(v) for k, v in record.items()})

            result = {
                "success": True,
                "input": {
                    "plan_contract": plan_contract,
                    "start_date": start_date,
                    "end_date": end_date,
                },
                "url": current_url,
                "row_count": int(len(df)),
                "columns": list(df.columns),
                "preview_rows": preview_rows_cleaned,
                "all_rows": all_rows_cleaned,
                "note": "All available result pages were collected and parsed." if not df.empty else (
                    "The browser steps ran, but no results table was parsed. "
                    "The page layout or selectors may need adjustment, or the search returned no rows."
                ),
            }

            await context.close()
            await browser.close()
            return result

        except PlaywrightTimeoutError as exc:
            await context.close()
            await browser.close()
            return {
                "success": False,
                "error": f"Playwright timeout: {str(exc)}",
                "input": {
                    "plan_contract": plan_contract,
                    "start_date": start_date,
                    "end_date": end_date,
                },
                "url": page.url if page else url,
            }
        except Exception as exc:
            await context.close()
            await browser.close()
            return {
                "success": False,
                "error": str(exc),
                "input": {
                    "plan_contract": plan_contract,
                    "start_date": start_date,
                    "end_date": end_date,
                },
                "url": page.url if page else url,
            }



def analyze_results(scrape_result: Dict[str, Any]) -> Dict[str, Any]:
    if not scrape_result.get("success"):
        return {"success": False, "error": "Input JSON indicates the scrape failed."}

    rows = scrape_result.get("all_rows") or scrape_result.get("preview_rows") or []
    if not rows:
        return {"success": False, "error": "No rows found in the scrape output."}

    df_results = pd.DataFrame(rows)
    analysis_output: Dict[str, Any] = {
        "success": True,
        "row_count_used_for_analysis": int(len(df_results)),
    }

    if "Plan Timely" in df_results.columns:
        counts = df_results["Plan Timely"].astype(str).str.strip().value_counts()
        num_yes = int(counts.get("Yes", 0))
        denom_yes_no = int(counts.get("Yes", 0) + counts.get("No", 0))
        pct = round((num_yes / denom_yes_no) * 100, 2) if denom_yes_no > 0 else 0.0
        analysis_output["plan_timely_analysis"] = {
            "num_yes": num_yes,
            "denom_yes_no": denom_yes_no,
            "percentage": pct,
        }
    else:
        analysis_output["plan_timely_analysis"] = {"error": "'Plan Timely' column not found."}

    if "IRE Recon Decision" in df_results.columns:
        counts = df_results["IRE Recon Decision"].astype(str).str.strip().value_counts()
        num_unfavorable = int(counts.get("Unfavorable", 0))
        denom = int(
            counts.get("Favorable", 0)
            + counts.get("Unfavorable", 0)
            + counts.get("Partially Favorable", 0)
        )
        pct = round((num_unfavorable / denom) * 100, 2) if denom > 0 else 0.0
        analysis_output["ire_recon_decision_analysis"] = {
            "num_unfavorable": num_unfavorable,
            "denom_favorable_unfavorable_partially": denom,
            "percentage": pct,
        }
    else:
        analysis_output["ire_recon_decision_analysis"] = {"error": "'IRE Recon Decision' column not found."}

    return analysis_output



def summarize_with_llm(scrape_result: Dict[str, Any], analysis_result: Dict[str, Any]) -> str:
    api_key = get_openai_api_key()
    if not api_key:
        return "No OpenAI key found in Streamlit secrets, so only the structured results are shown below."

    llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0, api_key=api_key)
    prompt = (
        "You are summarizing Medicare appeals search results for a public Streamlit app. "
        "Write a concise executive summary in plain English. Mention the plan contract, date range, row count, "
        "whether the scrape succeeded, and the two analysis metrics when available. If a metric is missing, say so plainly.\n\n"
        f"SCRAPE_RESULT:\n{json.dumps(scrape_result, indent=2)}\n\n"
        f"ANALYSIS_RESULT:\n{json.dumps(analysis_result, indent=2)}"
    )
    return llm.invoke(prompt).content



def run_workflow(plan_contract: str, start_date: str, end_date: str) -> Tuple[Dict[str, Any], Dict[str, Any], pd.DataFrame, str]:
    ensure_playwright_browser()
    scrape_result = asyncio.run(scrape_medicare_appeals(plan_contract, start_date, end_date))
    analysis_result = analyze_results(scrape_result)

    rows = scrape_result.get("all_rows") or []
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    summary = summarize_with_llm(scrape_result, analysis_result)
    return scrape_result, analysis_result, df, summary


# -----------------------------
# UI
# -----------------------------
st.title("📋 Medicare Appeals Search Agent")
st.caption("Search the Medicare Appeals site, collect all visible result pages, analyze the results, and optionally generate an OpenAI summary.")

with st.sidebar:
    st.header("Configuration")
    has_key = bool(get_openai_api_key())
    st.write(f"OpenAI summary available: {'Yes' if has_key else 'No'}")
    st.info(
        "For maximum privacy, do not paste your API key into the app UI. "
        "Store it in Streamlit Community Cloud Secrets as OPENAI_API_KEY."
    )

with st.form("search_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        plan_contract = st.text_input("H Contract #", value="H5215", help="Example: H5215")
    with col2:
        start_date_value = st.date_input("Start Date", value=date(2025, 1, 1))
    with col3:
        end_date_value = st.date_input("End Date", value=date(2025, 12, 1))

    submitted = st.form_submit_button("Run search", use_container_width=True)

if submitted:
    try:
        validated_contract = validate_plan_contract(plan_contract)
        start_date = validate_short_date(streamlit_date_to_short_str(start_date_value))
        end_date = validate_short_date(streamlit_date_to_short_str(end_date_value))
        validate_date_order(start_date, end_date)

        with st.spinner("Running browser automation and collecting all result pages..."):
            scrape_result, analysis_result, df_results, summary = run_workflow(
                validated_contract,
                start_date,
                end_date,
            )

        st.subheader("Summary")
        st.write(summary)

        st.subheader("Search details")
        left, right = st.columns(2)
        with left:
            st.metric("Rows returned", scrape_result.get("row_count", 0))
        with right:
            st.metric("Scrape success", "Yes" if scrape_result.get("success") else "No")

        if scrape_result.get("url"):
            st.write(f"Results URL: {scrape_result['url']}")
        if scrape_result.get("note"):
            st.info(scrape_result["note"])

        st.subheader("Analysis")
        metric_col1, metric_col2 = st.columns(2)

        timely = analysis_result.get("plan_timely_analysis", {})
        ire = analysis_result.get("ire_recon_decision_analysis", {})

        with metric_col1:
            if "percentage" in timely:
                st.metric("Plan Timely %", f"{timely['percentage']}%")
                st.caption(f"Yes: {timely['num_yes']} / Yes+No: {timely['denom_yes_no']}")
            else:
                st.warning(timely.get("error", "Plan Timely analysis unavailable."))

        with metric_col2:
            if "percentage" in ire:
                st.metric("IRE Unfavorable %", f"{ire['percentage']}%")
                st.caption(
                    "Unfavorable: "
                    f"{ire['num_unfavorable']} / Favorable+Unfavorable+Partially Favorable: "
                    f"{ire['denom_favorable_unfavorable_partially']}"
                )
            else:
                st.warning(ire.get("error", "IRE Recon Decision analysis unavailable."))

        st.subheader("Results table")
        if df_results.empty:
            st.warning("No rows were parsed into a dataframe.")
        else:
            st.dataframe(df_results, use_container_width=True)
            csv_bytes = df_results.to_csv(index=False).encode("utf-8")
            filename = f"medicare_appeals_{validated_contract}_{start_date.replace('/', '-')}_{end_date.replace('/', '-')}.csv"
            st.download_button(
                "Download results as CSV",
                data=csv_bytes,
                file_name=filename,
                mime="text/csv",
            )

        with st.expander("Raw scrape JSON"):
            st.json(scrape_result)

        with st.expander("Raw analysis JSON"):
            st.json(analysis_result)

    except Exception as exc:
        st.error(str(exc))
else:
    st.write("Enter the H Contract #, start date, and end date, then click **Run search**.")
