from .normalization import normalize_invoice

REQUIRED = ("vendor_name", "invoice_number", "invoice_date", "total_amount")

def validate_invoice(invoice: dict):
    normalized = normalize_invoice(invoice)
    errors, warnings = [], []
    for field in REQUIRED:
        if normalized.get(field) in (None, ""):
            errors.append(f"Required field is missing: {field.replace('_', ' ')}.")
    total = normalized.get("total_amount")
    if total is not None and total <= 0:
        errors.append("Invoice total must be greater than zero.")
    subtotal, tax = normalized.get("subtotal"), normalized.get("tax_amount")
    if total is not None and subtotal is not None and tax is not None:
        expected = round(subtotal + tax, 2)
        if abs(expected - total) > max(0.05, total * 0.005):
            warnings.append(f"Subtotal + tax ({expected:.2f}) does not equal invoice total ({total:.2f}).")
    if normalized.get("currency") is None:
        warnings.append("Currency was not identified; currency compatibility cannot be confirmed.")
    return normalized, {"is_valid": not errors, "errors": errors, "warnings": warnings}
