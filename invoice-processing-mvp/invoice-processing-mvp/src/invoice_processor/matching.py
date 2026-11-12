import pandas as pd
from rapidfuzz import fuzz, process

def _truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y", "approved", "active"}

def resolve_vendor(invoice_vendor, vendors: pd.DataFrame):
    if not invoice_vendor or vendors is None or vendors.empty:
        return {"vendor": None, "score": 0, "match_type": "none"}
    names = vendors["vendor_name"].fillna("").astype(str).tolist()
    match = process.extractOne(invoice_vendor, names, scorer=fuzz.token_set_ratio)
    if not match:
        return {"vendor": None, "score": 0, "match_type": "none"}
    _, score, idx = match
    row = vendors.iloc[idx].to_dict()
    return {"vendor": row, "score": int(score),
            "match_type": "exact" if score == 100 else "fuzzy"}

def match_purchase_order(invoice: dict, vendors: pd.DataFrame, pos: pd.DataFrame):
    vendor_match = resolve_vendor(invoice.get("vendor_name"), vendors)
    vendor = vendor_match["vendor"]
    vendor_id = str(vendor.get("vendor_id")) if vendor else None
    candidates = pos.copy()
    if vendor_id and "vendor_id" in candidates.columns:
        candidates = candidates[candidates["vendor_id"].astype(str) == vendor_id]
    explicit = invoice.get("po_number")
    if explicit:
        exact = pos[pos["po_number"].astype(str).str.strip().str.casefold() ==
                    str(explicit).strip().casefold()]
        if not exact.empty:
            row = exact.iloc[0].to_dict()
            same_vendor = (not vendor_id or str(row.get("vendor_id")) == vendor_id)
            return {"po": row, "po_number": str(row.get("po_number")),
                    "score": 100 if same_vendor else 55,
                    "match_type": "exact_po" if same_vendor else "po_vendor_conflict",
                    "vendor_match": vendor_match}
    if candidates.empty:
        return {"po": None, "po_number": None, "score": 0, "match_type": "none",
                "vendor_match": vendor_match}
    inv_total = invoice.get("total_amount")
    best = None
    for _, row in candidates.iterrows():
        amount = pd.to_numeric(row.get("total_amount"), errors="coerce")
        amount_score = 0
        if inv_total is not None and pd.notna(amount) and float(amount) > 0:
            diff_pct = abs(float(inv_total) - float(amount)) / float(amount) * 100
            amount_score = max(0, 100 - min(diff_pct * 8, 100))
        name_score = vendor_match["score"]
        score = round(0.65 * name_score + 0.35 * amount_score)
        if best is None or score > best[0]:
            best = (score, row.to_dict())
    if best:
        return {"po": best[1], "po_number": str(best[1].get("po_number")),
                "score": best[0], "match_type": "inferred_candidate",
                "vendor_match": vendor_match}
    return {"po": None, "po_number": None, "score": 0, "match_type": "none",
            "vendor_match": vendor_match}

def amount_comparison(invoice: dict, po_match: dict, tolerance_percent: float):
    po = po_match.get("po")
    inv_total = invoice.get("total_amount")
    if not po or inv_total is None:
        return {"comparable": False, "within_tolerance": False, "variance": None,
                "variance_percent": None, "po_total": None}
    po_total = pd.to_numeric(po.get("total_amount"), errors="coerce")
    if pd.isna(po_total) or float(po_total) == 0:
        return {"comparable": False, "within_tolerance": False, "variance": None,
                "variance_percent": None, "po_total": None}
    variance = round(float(inv_total) - float(po_total), 2)
    variance_pct = round(abs(variance) / abs(float(po_total)) * 100, 3)
    return {"comparable": True, "within_tolerance": variance_pct <= tolerance_percent,
            "variance": variance, "variance_percent": variance_pct,
            "po_total": round(float(po_total), 2)}
