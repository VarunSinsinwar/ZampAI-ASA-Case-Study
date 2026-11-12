from pathlib import Path
from datetime import datetime, timezone
import uuid
import pandas as pd

from .ingestion import extract_document_text
from .extractor import extract_invoice
from .validation import validate_invoice
from .matching import match_purchase_order, amount_comparison
from .duplicates import file_fingerprint, check_duplicate
from .decision import decide

def _stage(stages, callback, name, detail, pct, status="completed"):
    stages.append({"stage": name, "status": status, "detail": detail})
    if callback:
        callback(name, detail, pct)

def _check_columns(df, required, label):
    if df is None:
        raise ValueError(f"{label} CSV is missing.")
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{label} CSV is missing required columns: {', '.join(missing)}")
    return df

def process_invoice(file_path, original_filename, vendors, purchase_orders,
                    po_line_items, store, tolerance_percent, use_llm, settings,
                    on_stage=None):
    run_id = str(uuid.uuid4())[:8].upper()
    stages = []
    vendors = _check_columns(vendors, ["vendor_id", "vendor_name", "approved"], "vendors")
    pos = _check_columns(purchase_orders, ["po_number", "vendor_id", "vendor_name",
                                           "currency", "total_amount", "status"], "purchase_orders")
    _stage(stages, on_stage, "Ingestion", f"Received {original_filename}; run ID {run_id}.", 8)
    fingerprint = file_fingerprint(file_path)

    def ocr_note(detail):
        if on_stage:
            on_stage("OCR routing", detail, 20)
    text, method = extract_document_text(file_path, settings.min_pdf_text_chars,
                                         settings.ocr_language, ocr_note)
    if not text.strip():
        raise ValueError("No readable text was extracted. Check scan quality and Tesseract installation.")
    _stage(stages, on_stage, "Document extraction",
           f"Extracted {len(text)} characters using {method}.", 28)
    raw_invoice = extract_invoice(text, use_llm=use_llm,
                                  api_key=settings.gemini_api_key,
                                  model=settings.gemini_model)
    raw_invoice["extraction_method"] = raw_invoice.get("extraction_method") or method
    _stage(stages, on_stage, "Structured extraction",
           f"Fields parsed using {raw_invoice['extraction_method']}; confidence label: {raw_invoice.get('extraction_confidence')}.", 42)
    invoice, validation = validate_invoice(raw_invoice)
    _stage(stages, on_stage, "Validation",
           f"{len(validation['errors'])} blocking field errors and {len(validation['warnings'])} warnings.", 55)
    po_match = match_purchase_order(invoice, vendors, pos)
    _stage(stages, on_stage, "Vendor / PO matching",
           f"Vendor score {po_match['vendor_match']['score']}%; PO candidate {po_match.get('po_number') or 'not found'}.", 68)
    amount_check = amount_comparison(invoice, po_match, tolerance_percent)
    duplicate = check_duplicate(store, invoice, fingerprint)
    _stage(stages, on_stage, "Duplicate detection",
           "Duplicate found." if duplicate["is_duplicate"] else "No previous duplicate found.", 80)
    decision = decide(invoice, validation, po_match["vendor_match"], po_match,
                      amount_check, duplicate, tolerance_percent)
    _stage(stages, on_stage, "Decision",
           f"{decision['status']}: {decision['summary']}", 92)
    result = {
        "run_id": run_id, "processed_at": datetime.now(timezone.utc).isoformat(),
        "filename": original_filename, "source_text_excerpt": text[:2500],
        "extraction_route": method, "invoice": invoice,
        "validation": validation,
        "vendor_match": {"vendor": po_match["vendor_match"].get("vendor"),
                         "score": po_match["vendor_match"].get("score"),
                         "match_type": po_match["vendor_match"].get("match_type")},
        "po_match": {"po": po_match.get("po"), "po_number": po_match.get("po_number"),
                     "score": po_match.get("score"), "match_type": po_match.get("match_type")},
        "amount_check": amount_check, "duplicate": duplicate,
        "decision": decision, "stages": stages,
        "configuration": {"tolerance_percent": tolerance_percent, "llm_enabled": bool(use_llm)}
    }
    store.save_run(result, original_filename, fingerprint)
    _stage(stages, on_stage, "Audit trail",
           "Run, decision, evidence and stage trace saved to SQLite.", 100)
    # Update stored result to include final audit stage.
    store.update_result(result, original_filename, fingerprint) if hasattr(store, "update_result") else None
    return result
