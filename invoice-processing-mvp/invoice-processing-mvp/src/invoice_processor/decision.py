def decide(invoice, validation, vendor_match, po_match, amount_check, duplicate,
           tolerance_percent):
    reasons = []
    if duplicate.get("is_duplicate"):
        reasons.append("Duplicate detected: " + duplicate.get("reason", "matching prior invoice."))
        return {"status": "REJECT", "summary": "This invoice appears to have already been processed.",
                "reasons": reasons}

    vendor = vendor_match.get("vendor")
    if vendor is None:
        reasons.append("Vendor could not be matched to the approved vendor register.")
    else:
        approved = str(vendor.get("approved", "")).strip().lower() in {
            "1", "true", "yes", "y", "approved", "active"
        }
        if not approved:
            reasons.append("Vendor is marked unapproved in the vendor register.")
            return {"status": "REJECT", "summary": "Vendor is not approved for payment.",
                    "reasons": reasons}
        if vendor_match.get("score", 0) < 85:
            reasons.append(f"Vendor match confidence is low ({vendor_match.get('score')}%).")

    reasons.extend(validation.get("errors", []))
    reasons.extend(validation.get("warnings", []))

    po = po_match.get("po")
    if po is None:
        reasons.append("No purchase order could be matched.")
    else:
        if po_match.get("match_type") != "exact_po":
            reasons.append(f"PO is an inferred candidate (match score {po_match.get('score')}%); confirm before payment.")
        if po_match.get("match_type") == "po_vendor_conflict":
            reasons.append("The referenced PO appears to belong to a different vendor.")
        status = str(po.get("status", "")).strip().lower()
        if status and status in {"closed", "cancelled", "canceled", "rejected", "void"}:
            reasons.append(f"PO status is {status}; it is not available for matching.")
        if amount_check.get("comparable"):
            if not amount_check["within_tolerance"]:
                reasons.append(
                    f"Invoice differs from PO by {amount_check['variance']:.2f} "
                    f"({amount_check['variance_percent']:.3f}%), exceeding the {tolerance_percent:.2f}% tolerance."
                )
        else:
            reasons.append("Invoice and PO totals could not be compared.")

        po_currency = str(po.get("currency", "")).upper().strip()
        inv_currency = str(invoice.get("currency", "")).upper().strip()
        if po_currency and inv_currency and po_currency != inv_currency:
            reasons.append(f"Currency mismatch: invoice {inv_currency} vs PO {po_currency}.")

    if reasons:
        return {"status": "REVIEW", "summary": "Human review is required before this invoice can be approved.",
                "reasons": reasons}
    return {"status": "APPROVE",
            "summary": "Required fields are present; approved vendor, exact PO, amount within tolerance and no duplicate.",
            "reasons": ["All configured approval checks passed."]}
