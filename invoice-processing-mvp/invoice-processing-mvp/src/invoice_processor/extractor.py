import json
import re
from .schemas import InvoiceData
from .normalization import parse_amount

def _first(patterns, text, flags=re.I | re.M):
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            return m.group(1).strip()
    return None

def local_extract(text: str):
    # Label-driven patterns cover common invoice layouts; fields remain nullable if not found.
    vendor = _first([
        r"(?im)^\s*(?:from|vendor|supplier)\s*[:\-]\s*(.+)$",
        r"(?im)^\s*([A-Z][A-Za-z0-9&.,'()\- ]{2,})\s*$"
    ], text)
    invoice_no = _first([
        r"(?:invoice\s*(?:no|number|#|id)\s*[:#\-]?\s*)([A-Z0-9][A-Z0-9\-\/._]+)",
        r"(?:inv\.?\s*#\s*)([A-Z0-9\-\/._]+)"
    ], text)
    invoice_date = _first([
        r"(?:invoice\s*date|date\s*of\s*invoice|bill\s*date)\s*[:\-]?\s*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})"
    ], text)
    due_date = _first([
        r"(?:due\s*date|payment\s*due)\s*[:\-]?\s*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})"
    ], text)
    po = _first([
        r"(?:purchase\s*order|p\.?o\.?|po)\s*(?:number|no\.?|#|ref(?:erence)?)?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\-\/._]+)"
    ], text)
    currency = _first([r"\b(USD|EUR|GBP|INR|CAD|AUD|SGD|AED)\b"], text)
    # Search from most specific labels to generic total labels.
    total_raw = _first([
        r"(?:grand\s*total|amount\s*due|balance\s*due|invoice\s*total|total\s*payable)\s*[:\-]?\s*(?:USD|EUR|GBP|INR|₹|\$|€|£)?\s*([(\-]?\d[\d,.\s]*\d|\d)",
        r"(?im)^\s*total\s*[:\-]?\s*(?:USD|EUR|GBP|INR|₹|\$|€|£)?\s*([(\-]?\d[\d,.\s]*\d|\d)\s*$"
    ], text)
    subtotal_raw = _first([r"(?:sub\s*total|subtotal)\s*[:\-]?\s*(?:₹|\$|€|£)?\s*([\d,.\s]+)"], text)
    tax_raw = _first([r"(?:tax|vat|gst)\s*(?:amount)?\s*[:\-]?\s*(?:₹|\$|€|£)?\s*([\d,.\s]+)"], text)
    data = {
        "vendor_name": vendor, "invoice_number": invoice_no, "invoice_date": invoice_date,
        "due_date": due_date, "po_number": po, "currency": currency,
        "subtotal": parse_amount(subtotal_raw), "tax_amount": parse_amount(tax_raw),
        "total_amount": parse_amount(total_raw), "line_items": [],
        "extraction_method": "local", "extraction_confidence": "low"
    }
    found = sum(bool(data[k]) for k in ("vendor_name", "invoice_number", "invoice_date", "total_amount"))
    if found >= 3:
        data["extraction_confidence"] = "medium"
    return data

def gemini_extract(text: str, api_key: str, model: str):
    from google import genai
    client = genai.Client(api_key=api_key)
    prompt = f"""
Extract invoice fields from the text below. Do not invent missing values.
Return only a JSON object with keys:
vendor_name, invoice_number, invoice_date, due_date, po_number, currency,
subtotal, tax_amount, total_amount, line_items.
line_items must be a list of objects with description, quantity, unit_price, tax_rate, line_total.
Use numbers for amounts and null for unknown fields. Keep date strings as printed.
INVOICE TEXT:
{text[:30000]}
"""
    response = client.models.generate_content(model=model, contents=prompt)
    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
    obj = json.loads(raw)
    obj["extraction_method"] = "gemini"
    obj["extraction_confidence"] = "model"
    return InvoiceData.model_validate(obj).model_dump()

def extract_invoice(text: str, use_llm=False, api_key="", model="gemini-2.0-flash"):
    local = local_extract(text)
    if use_llm and api_key and text.strip():
        try:
            ai = gemini_extract(text, api_key, model)
            # Do not lose fields the model leaves blank if the local parser found them.
            for key, value in local.items():
                if ai.get(key) in (None, "", []):
                    ai[key] = value
            return InvoiceData.model_validate(ai).model_dump()
        except Exception:
            pass
    return InvoiceData.model_validate(local).model_dump()
