from src.invoice_processor.decision import decide

def test_approve_exact_clean_match():
    invoice = {"total_amount": 102.0, "currency": "USD"}
    validation = {"errors": [], "warnings": []}
    vendor_match = {"vendor": {"approved": "true"}, "score": 100}
    po_match = {"po": {"status": "open", "currency": "USD"}, "match_type": "exact_po"}
    amount = {"comparable": True, "within_tolerance": True}
    duplicate = {"is_duplicate": False}
    result = decide(invoice, validation, vendor_match, po_match, amount, duplicate, 2)
    assert result["status"] == "APPROVE"

def test_duplicate_rejected():
    result = decide({}, {"errors": [], "warnings": []}, {}, {}, {}, 
                    {"is_duplicate": True, "reason": "same invoice"}, 2)
    assert result["status"] == "REJECT"

def test_missing_po_review():
    result = decide({}, {"errors": [], "warnings": []},
                    {"vendor": {"approved": "true"}, "score": 100},
                    {"po": None}, {"comparable": False},
                    {"is_duplicate": False}, 2)
    assert result["status"] == "REVIEW"
