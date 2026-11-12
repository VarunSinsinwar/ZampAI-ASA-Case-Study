from datetime import datetime
import re
from typing import Any

def clean_text(value: Any):
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value)).strip(" \t\r\n:;,#")
    return value or None

def parse_amount(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    s = str(value).strip().replace(" ", "")
    # Support 1,234.56 and 1.234,56 without treating currency symbols as digits.
    s = re.sub(r"[^\d,.\-()]", "", s)
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        tail = s.rsplit(",", 1)[-1]
        s = s.replace(",", ".") if len(tail) in (1, 2) else s.replace(",", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None

def normalize_date(value):
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                "%d %b %Y", "%b %d, %Y", "%d %B %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return s

def normalize_invoice(data: dict):
    out = dict(data)
    for key in ("vendor_name", "invoice_number", "po_number", "currency"):
        out[key] = clean_text(out.get(key))
    for key in ("subtotal", "tax_amount", "total_amount"):
        out[key] = parse_amount(out.get(key))
    out["invoice_date"] = normalize_date(out.get("invoice_date"))
    out["due_date"] = normalize_date(out.get("due_date"))
    out["currency"] = (out.get("currency") or "").upper() or None
    return out
