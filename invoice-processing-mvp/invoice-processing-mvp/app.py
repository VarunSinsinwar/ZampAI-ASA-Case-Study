from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from src.invoice_processor.config import Settings
from src.invoice_processor.pipeline import process_invoice
from src.invoice_processor.storage import AuditStore

load_dotenv()
st.set_page_config(page_title="InvoiceFlow | AP Automation", page_icon="🧾", layout="wide")

ROOT = Path(__file__).parent
settings = Settings.from_env(ROOT)
store = AuditStore(settings.database_path)

st.markdown("""
<style>
.block-container {padding-top: 1.7rem; padding-bottom: 2rem;}
.metric-card {background: var(--secondary-background-color); padding: 15px 18px; border-radius: 12px;}
.stage {padding: 9px 12px; border-left: 3px solid #3b82f6; margin: 5px 0; background: var(--secondary-background-color); border-radius: 4px;}
.small-muted {color: #8b949e; font-size: .85rem;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🧾 InvoiceFlow")
    st.caption("AI-assisted accounts payable")
    page = st.radio("Workspace", ["Process invoice", "Run history", "Configuration & help"])
    st.divider()
    st.subheader("Procurement data")
    st.caption("Use your existing CSV files. No sample data is generated.")
    vendors_file = st.file_uploader("vendors.csv", type="csv", key="vendors")
    pos_file = st.file_uploader("purchase_orders.csv", type="csv", key="pos")
    lines_file = st.file_uploader("po_line_items.csv", type="csv", key="lines")
    data_dir = st.text_input("Or use a local data folder", value=str(settings.data_dir))
    st.caption("CSV uploads take precedence over files in the folder.")

def load_table(upload, path):
    if upload is not None:
        return pd.read_csv(upload)
    if Path(path).exists():
        return pd.read_csv(path)
    return None

def procurement_data():
    base = Path(data_dir).expanduser()
    v = load_table(vendors_file, base / "vendors.csv")
    p = load_table(pos_file, base / "purchase_orders.csv")
    l = load_table(lines_file, base / "po_line_items.csv")
    return v, p, l

def status_color(status):
    return {"APPROVE": "green", "REVIEW": "orange", "REJECT": "red"}.get(status, "gray")

if page == "Process invoice":
    st.title("Invoice processing")
    st.write("Upload an invoice and follow it through extraction, validation, PO matching and a reasoned AP decision.")
    left, right = st.columns([1.15, 0.85])
    with left:
        invoice = st.file_uploader("Choose an invoice", type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"])
        with st.expander("Processing controls", expanded=True):
            tolerance = st.number_input("PO amount tolerance (%)", min_value=0.0, max_value=25.0,
                                         value=float(settings.tolerance_percent), step=0.5)
            use_llm = st.toggle("Use optional Gemini extraction", value=settings.use_llm and bool(settings.gemini_api_key),
                                help="Requires GEMINI_API_KEY. If unavailable, local extraction is used.")
            st.caption("AI assists with reading the invoice. Approval rules remain deterministic.")
        run = st.button("▶ Process invoice", type="primary", disabled=invoice is None, use_container_width=True)
    with right:
        st.subheader("What happens")
        for label in ["1 · Read PDF / image", "2 · OCR if needed", "3 · Extract structured fields",
                      "4 · Validate invoice", "5 · Match vendor and PO", "6 · Check duplicates",
                      "7 · Decide and record audit trail"]:
            st.markdown(f'<div class="stage">{label}</div>', unsafe_allow_html=True)

    if run and invoice:
        vendors, pos, lines = procurement_data()
        if vendors is None or pos is None:
            st.error("Procurement data is missing. Upload vendors.csv and purchase_orders.csv, or point the data folder to their location.")
        else:
            suffix = Path(invoice.name).suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(invoice.getvalue())
                temp_path = tmp.name
            progress = st.progress(0)
            status_box = st.empty()
            stage_log = []
            def on_stage(name, detail, pct):
                stage_log.append({"stage": name, "detail": detail})
                progress.progress(min(int(pct), 100))
                status_box.info(f"**{name}** — {detail}")
            try:
                result = process_invoice(
                    file_path=temp_path, original_filename=invoice.name,
                    vendors=vendors, purchase_orders=pos,
                    po_line_items=lines, store=store,
                    tolerance_percent=float(tolerance), use_llm=use_llm,
                    settings=settings, on_stage=on_stage
                )
                st.session_state["last_result"] = result
                st.session_state["last_stages"] = stage_log
                progress.progress(100)
                status_box.success("Processing completed.")
            except Exception as exc:
                st.exception(exc)
            finally:
                os.unlink(temp_path)

    result = st.session_state.get("last_result")
    if result:
        st.divider()
        st.subheader("Decision")
        decision = result["decision"]["status"]
        a, b, c, d = st.columns(4)
        a.metric("Outcome", decision)
        b.metric("Invoice total", f'{result["invoice"].get("currency") or ""} {result["invoice"].get("total_amount") if result["invoice"].get("total_amount") is not None else "—"}')
        c.metric("PO match", result["po_match"].get("po_number") or "Not matched")
        d.metric("Duplicate", "Yes" if result["duplicate"]["is_duplicate"] else "No")
        st.markdown(f"**Reason:** {result['decision']['summary']}")
        if result["decision"]["reasons"]:
            for reason in result["decision"]["reasons"]:
                st.write(f"- {reason}")
        tabs = st.tabs(["Extracted invoice", "PO comparison", "Processing trace", "Audit JSON"])
        with tabs[0]:
            st.json(result["invoice"])
            if result["validation"]["warnings"]:
                st.warning("Validation warnings: " + "; ".join(result["validation"]["warnings"]))
            if result["validation"]["errors"]:
                st.error("Validation errors: " + "; ".join(result["validation"]["errors"]))
        with tabs[1]:
            st.json(result["po_match"])
            st.json(result["amount_check"])
        with tabs[2]:
            for item in result["stages"]:
                st.markdown(f"**{item['stage']}** · {item['status']}  \n{item['detail']}")
        with tabs[3]:
            st.download_button("Download result JSON", json.dumps(result, indent=2, default=str),
                               file_name=f"invoice_run_{result['run_id']}.json", mime="application/json")
            st.json(result)

elif page == "Run history":
    st.title("Run history")
    records = store.list_runs(limit=500)
    if not records:
        st.info("No invoices have been processed yet.")
    else:
        df = pd.DataFrame(records)
        x1, x2, x3, x4 = st.columns(4)
        x1.metric("Total runs", len(df))
        x2.metric("Approved", int((df["decision"] == "APPROVE").sum()))
        x3.metric("Needs review", int((df["decision"] == "REVIEW").sum()))
        x4.metric("Rejected", int((df["decision"] == "REJECT").sum()))
        counts = df["decision"].value_counts().rename_axis("Decision").reset_index(name="Count")
        st.plotly_chart(px.pie(counts, names="Decision", values="Count", hole=.55,
                               title="Decision distribution"), use_container_width=True)
        st.dataframe(df[["run_id", "created_at", "filename", "vendor_name", "invoice_number",
                         "po_number", "total_amount", "decision", "summary"]], use_container_width=True,
                     hide_index=True)
        selected = st.selectbox("Inspect a run", df["run_id"].tolist())
        if selected:
            detail = store.get_run(selected)
            if detail:
                st.json(detail)
                st.download_button("Download selected run JSON", json.dumps(detail, indent=2, default=str),
                                   file_name=f"{selected}.json", mime="application/json")

else:
    st.title("Configuration & operating assumptions")
    st.markdown("""
### Required procurement CSVs

| File | Required columns |
|---|---|
| vendors.csv | vendor_id, vendor_name, approved, currency |
| purchase_orders.csv | po_number, vendor_id, vendor_name, currency, total, status |
| po_line_items.csv | po_number, vendor_id, description, quantity, unit_price, line_amount |

Line items are optional for the MVP; the first two files are required for reliable PO matching.

### Supported inputs
PDF (text-based or scanned), PNG, JPG/JPEG, TIFF, BMP and WEBP. Scanned PDFs are rendered page-by-page with PyMuPDF and passed to Tesseract OCR.

### Decision policy
- **APPROVE:** required invoice fields are present, vendor is approved, PO match is reliable, amount is within tolerance, and no duplicate is found.
- **REVIEW:** missing/ambiguous data, uncertain PO match, missing PO, or amount variance outside tolerance.
- **REJECT:** confirmed duplicate or vendor explicitly marked unapproved.

This is an AP triage MVP, not a payment execution system. A human should review REVIEW and REJECT outcomes before taking action.

### Optional AI extraction
Set `GEMINI_API_KEY` in `.env` to enable Gemini structured extraction. Without a key, deterministic text extraction is used. The decision engine does not depend on an LLM.

### OCR prerequisite
Install the Tesseract OCR engine on the machine and ensure `tesseract` is available on PATH. Python package installation alone does not install the OCR executable.
""")
    st.code("streamlit run app.py", language="bash")
